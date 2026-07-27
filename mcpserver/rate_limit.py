"""Rate limiting for the MCP endpoint.

A thin adapter over ``api/rate_limit.py`` rather than a second limiter. Sharing
the buckets is the point: one credential gets one budget across both surfaces,
so a client cannot double its allowance by splitting traffic between ``/api``
and ``/mcp``. It also means the suite's ``_reset_rate_limiter`` fixture already
isolates MCP tests, and ``API_RATE_LIMIT_PER_MIN`` remains the single knob.

The adapter exists only because ``/mcp`` is a raw ASGI route: it gets no FastAPI
dependency injection, and the upstream limiter signals rejection by raising
``HTTPException``, which nothing would catch here.
"""

from typing import Optional

from fastapi import HTTPException
from starlette.requests import Request

from api.rate_limit import rate_limit as _rate_limit


async def check_rate_limit(request: Request) -> Optional[str]:
    """Return a ``Retry-After`` value when the caller is over its limit.

    ``None`` means the request may proceed. Reads only headers and
    ``request.client``, so the request body is left intact for the transport.
    """
    try:
        await _rate_limit(request)
    except HTTPException as exc:
        return (exc.headers or {}).get('Retry-After', '60')
    return None
