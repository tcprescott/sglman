"""Frontend initialization for the SGL On Site FastAPI application.

Sets up NiceGUI pages and integrates them with the FastAPI app.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from nicegui import app, ui

from application.utils.environment import get_platform_host, is_production, validate_security_config
from middleware.auth import AuthMiddleware
from middleware.error_handlers import register_error_handlers
from middleware.tenant import TenantMiddleware, TransportPrefixMiddleware
from pages import (
    admin,
    auth,
    challonge_oauth,
    equipment,
    home,
    platform,
    qualifiers,
    racetime_oauth,
    twitch_oauth,
    volunteer,
)

_ui_logger = logging.getLogger('sglman.ui')

# Order matters: Starlette runs the last-added middleware outermost, and
# ui.run_with() adds NiceGUI's session middleware afterwards (outermost of all).
# So execution is session -> transport-strip -> tenant -> auth: transport paths
# (/t/<slug>/_nicegui, /_nicegui_ws, /static, /sw.js — http AND websocket) are
# un-prefixed first so NiceGUI's assets and socket.io resolve; then the tenant is
# resolved and the ASGI path rewritten before AuthMiddleware reads the (now
# unprefixed) path. TransportPrefixMiddleware is added last (outermost of ours)
# and is pure-ASGI so it also handles the websocket scope BaseHTTPMiddleware skips.
app.add_middleware(AuthMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(TransportPrefixMiddleware)


@app.on_exception
def _handle_unhandled_ui_exception(exc: Exception) -> None:
    """Backstop for event handlers that miss the ValueError->ui.notify wrap:
    log the traceback (reaches Sentry) and, when a UI context is available,
    surface a generic notice so a failure is visible-but-generic rather than
    silent. Never raises itself."""
    _ui_logger.exception('Unhandled exception in a UI event handler', exc_info=exc)
    try:
        ui.notify('Something went wrong. Please try again.', color='negative')
    except Exception:
        pass


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles subclass that disables caching in development mode."""
    
    def __init__(self, *args, **kwargs):
        self.is_dev = os.environ.get('ENVIRONMENT', 'development') == 'development'
        super().__init__(*args, **kwargs)
    
    async def __call__(self, scope, receive, send):
        if self.is_dev and scope['type'] == 'http':
            # Wrap the send function to add no-cache headers
            async def send_wrapper(message):
                if message['type'] == 'http.response.start':
                    headers = list(message.get('headers', []))
                    # Remove any existing cache-control headers
                    headers = [h for h in headers if h[0].lower() != b'cache-control']
                    # Add no-cache headers
                    headers.append((b'cache-control', b'no-cache, no-store, must-revalidate'))
                    headers.append((b'pragma', b'no-cache'))
                    headers.append((b'expires', b'0'))
                    message['headers'] = headers
                await send(message)
            await super().__call__(scope, receive, send_wrapper)
        else:
            await super().__call__(scope, receive, send)


def init(fastapi_app: FastAPI) -> None:
    """
    Initialize the frontend by registering NiceGUI pages and attaching them to the FastAPI app.

    Args:
        fastapi_app (FastAPI): The FastAPI application instance to integrate with NiceGUI.
    """
    # Refuse to start with an insecure session/DB configuration.
    validate_security_config()

    # Log the resolved platform host so a proxy that isn't forwarding Host (which
    # would make every configured custom domain silently render the platform
    # surface) is diagnosable from startup logs.
    logging.getLogger('sglman').info(
        'Tenant routing: PLATFORM_HOST=%s (path mode /t/<slug> + host mode for custom domains)',
        get_platform_host(),
    )

    # Mount static files directory with no-cache in development
    fastapi_app.mount("/static", NoCacheStaticFiles(directory="static"), name="static")

    # Serve the service worker from the site root: a worker registered under the
    # /static/ path can only control /static/* clients, so it could never take
    # control of the app's start_url ('/'). Root scope is required for install.
    @fastapi_app.get('/sw.js', include_in_schema=False)
    async def _service_worker() -> FileResponse:
        # no-cache so an updated worker is always revalidated — matches the
        # NoCacheStaticFiles treatment of /static and avoids a stale SW pinning
        # old behavior (a fresh worker is what re-fetches everything else).
        return FileResponse(
            'static/sw.js',
            media_type='text/javascript',
            headers={'Cache-Control': 'no-cache'},
        )

    auth.create()
    challonge_oauth.create()
    twitch_oauth.create()
    racetime_oauth.create()
    admin.create()
    home.create()
    volunteer.create()
    equipment.create()
    platform.create()
    qualifiers.create()
    ui.run_with(
        fastapi_app,
        # mount_path='/gui',  # NOTE this can be omitted if you want the paths passed to @ui.page to be at the root
        title='SGL On Site',
        # viewport-fit=cover lets the header/footer bleed into the iOS safe-area
        # insets so the app reads edge-to-edge when installed to the home screen.
        viewport='width=device-width, initial-scale=1, viewport-fit=cover',
        favicon='static/icons/icon-192.png',
        storage_secret=(os.environ.get('STORAGE_SECRET') or '').strip(),  # required; enforced by validate_security_config()
        # Mark the session cookie Secure in production so the signed cookie
        # carrying the auth state is never sent over plaintext HTTP. Left off in
        # development so local http:// keeps working.
        session_middleware_kwargs={'https_only': is_production(), 'same_site': 'lax'},
    )
    register_error_handlers(fastapi_app)