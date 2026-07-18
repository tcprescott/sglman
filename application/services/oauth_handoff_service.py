"""Design B — cross-host login handoff for custom domains.

When ``HOST_OAUTH_MODE=handoff``, Discord OAuth always completes on the platform
host (one registered redirect URI, regardless of how many custom domains exist —
unlike Design A, which needs a registered URI per domain). The platform-host
callback then **mints** a short-lived, single-use, host-bound token and redirects
the browser to the target custom domain's ``/session/claim``, which **claims** it
and writes the host-local session so the auth cookie lands on the right host.

Why this is safe despite a token travelling in a URL:

- **Single-use.** The token's nonce is popped from an in-process store on first
  claim; a replay after the victim's own claim finds nothing. (The store is
  in-memory, matching the app's single-worker deployment — the same precondition
  the tenant-resolution caches already rely on. It is *not* shared across
  workers; a multi-worker deployment would need a shared store.)
- **Short TTL.** The signer enforces ``_TTL_SECONDS``; a leaked URL (browser
  history / ``Referer``) is only briefly replayable, and the redirect→claim round
  trip is sub-second in practice.
- **Host-bound.** The target host is signed into the token *and* held in the
  store, and the claim rejects a token presented on any other host — so a token
  minted for ``foo.gg`` cannot be replayed against ``bar.gg``.
- **Identity carried server-side.** Only the nonce + host travel in the URL; the
  ``discord_id``/username/avatar live in the store, so no PII is exposed in the
  URL or logs.

This lives in ``application/services`` but, like the tenant caches, holds a small
module-level store rather than per-instance state; its functions are stateless
entry points over that store.
"""

import logging
import secrets
import time
from typing import Optional

from itsdangerous import BadData, URLSafeTimedSerializer

from application.utils.hostname import normalize_hostname

logger = logging.getLogger(__name__)

_SALT = 'sglman-oauth-handoff'
# Tight window: mint → browser redirect → claim is sub-second; 30s absorbs a slow
# client without leaving a leaked URL replayable for long.
_TTL_SECONDS = 30
# Bound the pending store so a flood of unclaimed mints can't grow it without
# limit. FIFO eviction (insertion-ordered dict), like the tenant caches.
_STORE_MAX = 4096

# nonce -> {'discord_id', 'username', 'avatar', 'host', 'next', 'expiry'}
_pending: dict[str, dict] = {}


def _serializer() -> URLSafeTimedSerializer:
    # Read STORAGE_SECRET lazily (validated at startup) so a test/tooling override
    # applies without reimporting. The shared secret ties mint and claim together.
    import os
    return URLSafeTimedSerializer(os.environ.get('STORAGE_SECRET') or '', salt=_SALT)


def _prune(now: float) -> None:
    """Drop expired entries (cheap, bounded); called on every mint."""
    expired = [n for n, p in _pending.items() if p['expiry'] <= now]
    for n in expired:
        _pending.pop(n, None)


def reset() -> None:
    """Clear the pending store (test isolation)."""
    _pending.clear()


def mint(*, discord_id, username: Optional[str], avatar: Optional[str],
         target_host: str, next_path: str, bind_commit: Optional[str] = None) -> Optional[str]:
    """Mint a handoff token for ``discord_id`` bound to ``target_host``.

    ``target_host`` must already be validated as a known active tenant domain by
    the caller; it is normalized here so the claim's host comparison is apples to
    apples. Returns ``None`` if the host is not normalizable.

    ``bind_commit`` is a hash the *initiating* browser committed to at ``/login``
    (the raw secret stays in that browser's custom-domain session). The claim
    route re-derives it from the browser's cookie and compares, so a token minted
    in one browser can't be delivered to another (login-CSRF / forced login).
    """
    host = normalize_hostname(target_host)
    if host is None:
        return None
    now = time.time()
    _prune(now)
    nonce = secrets.token_urlsafe(24)
    if nonce not in _pending and len(_pending) >= _STORE_MAX:
        _pending.pop(next(iter(_pending)), None)
    _pending[nonce] = {
        'discord_id': discord_id,
        'username': username,
        'avatar': avatar,
        'host': host,
        'next': next_path,
        'bind_commit': bind_commit,
        'expiry': now + _TTL_SECONDS,
    }
    return _serializer().dumps({'n': nonce, 'h': host})


def claim(token: str, request_host: str) -> Optional[dict]:
    """Validate + consume a handoff token presented on ``request_host``.

    Returns the stored payload (``discord_id``/``username``/``avatar``/``next``)
    on success, or ``None`` for an invalid, expired, wrong-host, or
    already-claimed token. Single-use: the nonce is popped whether or not the
    later host check passes, so a token can never be tried twice.
    """
    host = normalize_hostname(request_host)
    if host is None:
        return None
    try:
        data = _serializer().loads(token, max_age=_TTL_SECONDS)
    except BadData:
        return None
    if not isinstance(data, dict):
        return None
    nonce = data.get('n')
    signed_host = data.get('h')
    if not nonce:
        return None
    payload = _pending.pop(nonce, None)  # consume regardless of outcome (single-use)
    if payload is None:
        return None
    if payload['expiry'] <= time.time():
        return None
    # Host must match the token's signed host AND the store AND where it was
    # presented — a token minted for one domain is useless on any other.
    if signed_host != host or payload['host'] != host:
        logger.warning('OAuth handoff token host mismatch (presented on %r)', host)
        return None
    return payload
