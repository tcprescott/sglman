"""Answer ``/live`` statically when the Watch page is static, before NiceGUI does.

The live Watch page is a NiceGUI page, so building it at all costs the render
and the websocket the static rendering exists to avoid. The decision has to be
made ahead of NiceGUI's route, so it is made here: every ``GET``/``HEAD`` of
``/live`` is counted as an arrival, and when staff set the page static or a
rush has tripped it (:func:`pages.static_watch.serve_static_arrival`), the
cached static document goes back without NiceGUI seeing the request.

Installed inside ``TenantMiddleware`` so the tenant is resolved and the path
already unprefixed. Pure ASGI, so anything that is not ``/live`` costs a string
comparison.
"""

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

_WATCH_PATHS = ('/live', '/live/')


class WatchModeMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope['type'] == 'http'
            and scope.get('method') in ('GET', 'HEAD')
            and scope.get('path') in _WATCH_PATHS
        ):
            from pages.static_watch import serve_static_arrival

            response = await serve_static_arrival(Request(scope, receive))
            if response is not None:
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
