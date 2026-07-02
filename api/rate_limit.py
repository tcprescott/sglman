"""In-process rate limiting for the REST API.

The app runs single-worker (``uvicorn --workers 1``), so a per-process
fixed-window counter is sufficient and avoids an external dependency or shared
store. Requests are keyed by bearer token when present (so one client's tokens
are limited independently) and otherwise by client IP.

Attached as a dependency on the aggregating API router so it covers every REST
endpoint without touching the NiceGUI frontend mounted on the same app.
"""

import hashlib
import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request, status

from application.services.api_token_service import TOKEN_PREFIX


def _limit_per_minute() -> int:
    try:
        return max(1, int(os.environ.get('API_RATE_LIMIT_PER_MIN', '120')))
    except ValueError:
        return 120


_WINDOW_SECONDS = 60.0
# key -> timestamps of requests within the current window
_hits: Dict[str, Deque[float]] = defaultdict(deque)
_last_sweep = 0.0


def _sweep(now: float) -> None:
    """Drop keys whose window has fully expired so idle/garbage keys don't
    accumulate. Runs at most once per window."""
    global _last_sweep
    if now - _last_sweep < _WINDOW_SECONDS:
        return
    _last_sweep = now
    cutoff = now - _WINDOW_SECONDS
    for key in [k for k, b in _hits.items() if not b or b[-1] < cutoff]:
        del _hits[key]


def _trust_forwarded_for() -> bool:
    """Whether to derive the client IP from ``X-Forwarded-For``.

    Off by default: the header is client-controlled and trivially spoofable, so
    trusting it would let an attacker evade IP-based limiting by rotating it.
    Enable only when the app sits behind a reverse proxy that overwrites the
    header with the real client IP.
    """
    return os.environ.get('TRUST_PROXY_FORWARDED_FOR', '').strip().lower() in (
        '1', 'true', 'yes', 'on',
    )


def _client_ip_key(request: Request) -> str:
    if _trust_forwarded_for():
        forwarded = request.headers.get('x-forwarded-for')
        if forwarded:
            return f'ip:{forwarded.split(",")[0].strip()}'
    return f'ip:{request.client.host if request.client else "unknown"}'


def _client_key(request: Request) -> str:
    auth = request.headers.get('authorization')
    if auth:
        token = auth[7:].strip() if auth[:7].lower() == 'bearer ' else auth.strip()
        # Only bucket by a *well-formed* token so each real token is limited
        # independently. Garbage/rotating tokens fall through to the IP key so a
        # flood of random bearer values can't get a fresh bucket each request
        # (bypass) or grow _hits without bound. Store only a hash, never the raw
        # secret, as the key.
        if token.startswith(TOKEN_PREFIX) and len(token) >= len(TOKEN_PREFIX) + 20:
            return f'token:{hashlib.sha256(token.encode()).hexdigest()}'
    return _client_ip_key(request)


async def rate_limit(request: Request) -> None:
    """Reject the request with 429 when its key exceeds the per-minute limit."""
    limit = _limit_per_minute()
    key = _client_key(request)
    now = time.monotonic()
    window_start = now - _WINDOW_SECONDS

    bucket = _hits[key]
    while bucket and bucket[0] < window_start:
        bucket.popleft()

    if len(bucket) >= limit:
        retry_after = max(1, int(bucket[0] + _WINDOW_SECONDS - now) + 1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail='Rate limit exceeded',
            headers={'Retry-After': str(retry_after)},
        )

    bucket.append(now)
