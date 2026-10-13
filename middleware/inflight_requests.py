"""Name the requests that hold a shutdown open.

uvicorn waits for every in-flight request before running the lifespan shutdown.
With ``--timeout-graceful-shutdown`` it cancels whatever is left once the
deadline passes, but only logs a count ("Cancel 3 running task(s)"). This
middleware logs each cancelled request's method, path and age, so a restart
that stalls on "Waiting for connections to close" says which route did it.

``_before_send`` in ``application/utils/sentry.py`` drops uvicorn's own
cancellation errors, which fire on every deploy, so this warning (shipped to
Sentry Logs) is the record of what a shutdown cut off.

Pure ASGI rather than ``BaseHTTPMiddleware``: it must wrap websockets too, and
must see the ``CancelledError`` raised inside the request task.
"""

import asyncio
import logging
import time

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger('wizzrobe.shutdown')


class InFlightRequestLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] not in ('http', 'websocket'):
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        try:
            await self.app(scope, receive, send)
        except asyncio.CancelledError:
            logger.warning(
                'Request cancelled while still open: %s %s (open %.1fs)',
                scope.get('method', 'WEBSOCKET'), scope.get('path', '?'),
                time.perf_counter() - started,
            )
            raise
