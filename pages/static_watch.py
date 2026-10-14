"""The Watch page's static rendering, and the switch that serves it at ``/live``.

``/live`` is normally a live NiceGUI page (``pages/live_watch.py``). Each live
reader is a websocket, and the app admits about ten new ones a second, so when
staff set the page to static, or a rush of arrivals trips it there
(:mod:`application.utils.live_audience`), :class:`middleware.watch_mode.WatchModeMiddleware`
answers ``/live`` from here before NiceGUI ever sees the request: one render per
change, shared by every reader, through the static bracket views' cache and
HTTP validators (:mod:`pages.static_brackets`).

``/live/static`` serves the same document at any time. The static page
refetches it once a minute to update itself in place, which is also how the
staff card counts static readers.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Request
from fastapi.responses import Response
from nicegui import app

from application.tenant_context import get_current_tenant_id
from application.utils import live_audience
from pages.static_brackets import _cache, _conditional, _no_store, _respond
from pages.watch_data import get_watch_view, watch_settings, watch_version
from theme.watch_view import render_watch_document

STATIC_PATH = '/live/static'


async def static_watch_response(request: Request, tenant_id: int) -> Response:
    """The cached static Watch page, or a 304 when the reader already has it."""
    root = request.scope.get('root_path', '') or ''
    key = f'watch:{watch_version(tenant_id)}:{root}'
    cached = _cache.get(tenant_id, key)
    if cached is not None:
        return _conditional(request, cached.etag, cached.body)
    view = await get_watch_view(tenant_id)
    body = render_watch_document(view, root_path=root, refresh_url=f'{root}{STATIC_PATH}')
    return _respond(request, tenant_id, key, body)


async def serve_static_arrival(request: Request) -> Optional[Response]:
    """Count an arrival at ``/live``; answer it statically when the page is static.

    ``None`` means "live": let the request through to the NiceGUI page.
    """
    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        return None
    settings = await watch_settings(tenant_id)
    live_audience.record_arrival(tenant_id, settings.threshold if settings.auto_static else None)
    if settings.mode == 'static' or live_audience.is_tripped(tenant_id):
        return await static_watch_response(request, tenant_id)
    return None


def create() -> None:
    """Register ``/live/static``."""

    @app.api_route(STATIC_PATH, methods=['GET', 'HEAD'], include_in_schema=False)
    async def static_watch(request: Request) -> Response:
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return _no_store('Not found', 404)
        live_audience.record_static_read(tenant_id)
        return await static_watch_response(request, tenant_id)
