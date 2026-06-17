"""In-process rate limiting for the REST API.

The app runs single-worker (``uvicorn --workers 1``), so a per-process
fixed-window counter is sufficient and avoids an external dependency or shared
store. Requests are keyed by bearer token when present (so one client's tokens
are limited independently) and otherwise by client IP.

Attached as a dependency on the aggregating API router so it covers every REST
endpoint without touching the NiceGUI frontend mounted on the same app.
"""

import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request, status


def _limit_per_minute() -> int:
    try:
        return max(1, int(os.environ.get('API_RATE_LIMIT_PER_MIN', '120')))
    except ValueError:
        return 120


_WINDOW_SECONDS = 60.0
# key -> timestamps of requests within the current window
_hits: Dict[str, Deque[float]] = defaultdict(deque)


def _client_key(request: Request) -> str:
    auth = request.headers.get('authorization')
    if auth:
        # Bucket by the token itself so each token is limited independently;
        # never log or expose this value.
        return f'token:{auth}'
    forwarded = request.headers.get('x-forwarded-for')
    if forwarded:
        return f'ip:{forwarded.split(",")[0].strip()}'
    return f'ip:{request.client.host if request.client else "unknown"}'


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
