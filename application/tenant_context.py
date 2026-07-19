"""Request-time tenant context — the primitive the whole tenancy layer reads.

Logical multitenancy keys every scoped row on a ``tenant_id``. That id is
resolved once per request (from the URL by ``middleware/tenant.py``) and stashed
here in a :class:`~contextvars.ContextVar` so the service/repository layers can
read it without threading it through every signature by hand. Repositories still
take an *explicit* ``tenant_id`` (the contract); this contextvar is what services
read once via :func:`require_tenant_id` before passing it down.

**Why a contextvar and a fallback.** The HTTP middleware only sees the initial
page load. Once NiceGUI's websocket takes over, every UI event handler runs
*outside* any request — no Host header, no path prefix, and the contextvar set by
the middleware is gone. So resolution happens in two tiers:

1. the contextvar (set by the middleware for the HTTP request, and by
   :func:`tenant_scope` for background/no-request code); else
2. the current NiceGUI client's per-connection stash
   (``app.storage.client['tenant_id']``), written at page build while the
   middleware's contextvar was still set.

Everything that runs with neither — the Discord bot loop, the DM-queue worker,
the event-dispatch worker, the volunteer-reminder loop, ``background_tasks`` —
must wrap its work in an explicit :func:`tenant_scope`.

This module is a peer of ``application/services`` (like ``application/events``)
and is import-safe from every layer, including repositories. It lazy-imports
NiceGUI only inside the fallback so it stays usable with no UI context.
"""

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator, Optional

# None means "no tenant" — the platform surface (landing page, /platform) and
# any code that legitimately runs tenant-agnostically. require_tenant_id() is
# what turns a forgotten scope into a loud error rather than a silent leak.
_tenant_id_var: ContextVar[Optional[int]] = ContextVar('wizzrobe_tenant_id', default=None)


def set_tenant_id(tenant_id: Optional[int]) -> Token:
    """Set the ambient tenant id, returning a token to pass to :func:`reset_tenant_id`."""
    return _tenant_id_var.set(tenant_id)


def reset_tenant_id(token: Token) -> None:
    """Restore the tenant id the matching :func:`set_tenant_id` replaced."""
    _tenant_id_var.reset(token)


# Host mode: the request arrived on a tenant's own custom domain (not the
# platform host at /t/<slug>). Tracked alongside the tenant id because a few
# surfaces behave differently on a custom domain — chiefly the OAuth callback
# builder and the secondary-provider link flows, which cannot complete on a
# host whose session cookie the platform-host callback can't see. Default False
# means path mode / platform surface, exactly as before host routing existed.
_host_mode_var: ContextVar[bool] = ContextVar('wizzrobe_host_mode', default=False)


def set_host_mode(value: bool) -> Token:
    """Mark the ambient request host-mode, returning a token for :func:`reset_host_mode`."""
    return _host_mode_var.set(value)


def reset_host_mode(token: Token) -> None:
    """Restore the host-mode flag the matching :func:`set_host_mode` replaced."""
    _host_mode_var.reset(token)


def _client_stash_host_mode() -> bool:
    """Whether the current NiceGUI client was built in host mode (defensive)."""
    try:
        from nicegui import app
    except Exception:
        return False
    try:
        return bool(app.storage.client.get('host_mode'))
    except Exception:
        return False


def is_host_mode() -> bool:
    """True when the current request/connection is on a tenant's custom domain.

    Contextvar first (set by ``TenantMiddleware`` for the HTTP request), then the
    per-client stash (written at page build) so a websocket UI event handler —
    which runs after the request context is gone — can still tell host mode from
    path mode.
    """
    if _host_mode_var.get():
        return True
    return _client_stash_host_mode()


def stash_client_host_mode(value: bool) -> None:
    """Persist the host-mode flag onto the current NiceGUI client (page-build time).

    Only writes when host mode is active: path mode / platform surface leave the
    stash unset, which :func:`_client_stash_host_mode` reads back as ``False``.
    No-op when there is no client context. Safe because ``app.storage.client`` is
    per-connection and a connection never changes host — so a stale ``True`` can
    never linger (there is nothing to clear on a path-mode build).
    """
    if not value:
        return
    try:
        from nicegui import app
    except Exception:
        return
    try:
        app.storage.client['host_mode'] = True
    except Exception:
        pass


def _client_stash_tenant_id() -> Optional[int]:
    """The tenant id stashed on the current NiceGUI client, or None.

    Fully defensive: returns None whenever NiceGUI is unavailable or there is no
    active client context (the common case in tests and background workers), so
    resolution never raises just because the UI layer is absent.
    """
    try:
        from nicegui import app
    except Exception:
        return None
    try:
        return app.storage.client.get('tenant_id')
    except Exception:
        # app.storage.client raises when accessed outside a client/slot context.
        return None


def get_current_tenant_id() -> Optional[int]:
    """Resolve the current tenant id, or None: contextvar first, then client stash."""
    tid = _tenant_id_var.get()
    if tid is not None:
        return tid
    return _client_stash_tenant_id()


def require_tenant_id() -> int:
    """Return the current tenant id, raising if there is none.

    This raise is the safety net of the explicit-threading contract: a service
    that reaches the data layer with no tenant in scope fails loudly here instead
    of silently querying across tenants.
    """
    tid = get_current_tenant_id()
    if tid is None:
        raise RuntimeError(
            'No tenant in context. A tenant-scoped operation ran outside any '
            'request and without an explicit tenant_scope(). Wrap background / '
            'bot / worker code in `with tenant_scope(tenant_id):`.'
        )
    return tid


@contextmanager
def tenant_scope(tenant_id: Optional[int]) -> Iterator[None]:
    """Bind ``tenant_id`` as the ambient tenant for the duration of the block.

    Safe inside ``async`` code: the contextvar is set/reset synchronously around
    the ``yield`` and, because contextvars propagate across ``await`` within the
    same task, it stays active for everything awaited inside the block. Used by
    every no-request path (bot loop, DM/event workers, reminder loop,
    background_tasks) and to re-establish a tenant for a deferred coroutine.
    """
    token = _tenant_id_var.set(tenant_id)
    try:
        yield
    finally:
        _tenant_id_var.reset(token)


def stash_client_tenant_id(tenant_id: Optional[int]) -> None:
    """Persist the tenant id onto the current NiceGUI client (page-build time).

    Read back later by :func:`get_current_tenant_id` when a websocket UI event
    handler runs with the contextvar unset. No-op when there is no client
    context (e.g. during tests or a plain HTTP response).
    """
    if tenant_id is None:
        return
    try:
        from nicegui import app
    except Exception:
        return
    try:
        app.storage.client['tenant_id'] = tenant_id
    except Exception:
        pass
