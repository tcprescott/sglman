"""Frontend initialization for the Wizzrobe FastAPI application.

Sets up NiceGUI pages and integrates them with the FastAPI app.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from nicegui import app, ui

from application.utils.environment import get_platform_host, is_production, validate_security_config
from middleware.auth import AuthMiddleware
from middleware.error_handlers import register_error_handlers
from middleware.public_cache import PublicCacheMiddleware
from middleware.tenant import TenantMiddleware, TransportPrefixMiddleware
from pages import (
    admin,
    auth,
    brackets,
    cat_facts,
    challonge_oauth,
    equipment,
    equipment_labels,
    event_info,
    home,
    mcp_consent,
    platform,
    qualifiers,
    racetime_oauth,
    static_brackets,
    twitch_oauth,
    volunteer,
)

# Its own statement, and aliased: ruff's isort keeps an `as` import separate,
# and the bare name would shadow the `help` builtin in this module.
from pages import help as help_pages
from pages._oauth_link import register_link_handoff_pages
from theme.assets import cache_control
from theme.timer_teardown import is_timer_teardown_race

_ui_logger = logging.getLogger('wizzrobe.ui')

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
    # A timer whose page went away is not an error anyone can act on, and
    # reporting it buries the ones that are — see theme/timer_teardown.py.
    if is_timer_teardown_race(exc):
        _ui_logger.debug('Timer outlived its page; stopping quietly.')
        return
    _ui_logger.exception('Unhandled exception in a UI event handler', exc_info=exc)
    try:
        ui.notify('Something went wrong. Please try again.', color='negative')
    except Exception:
        pass


class VersionedStaticFiles(StaticFiles):
    """StaticFiles that states its cache policy instead of leaving it to chance.

    Development sends ``no-store`` so an edit shows up on reload. Production
    answers on the version stamp :func:`theme.assets.asset_url` puts in the URL:

    * stamped (``?v=<mtime>``) — ``immutable``, cached for a year. The URL
      changes when the file does, so a client never has to be told to re-fetch.
    * unstamped — ``must-revalidate`` against the ETag every time.

    The policy itself lives in :func:`theme.assets.cache_control`, beside the
    function that writes the stamp.
    """

    def __init__(self, *args, **kwargs):
        self.is_dev = os.environ.get('ENVIRONMENT', 'development') == 'development'
        super().__init__(*args, **kwargs)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await super().__call__(scope, receive, send)
            return

        policy = cache_control(scope.get('query_string', b''), is_dev=self.is_dev)

        async def send_wrapper(message):
            if message['type'] == 'http.response.start':
                headers = [
                    h for h in message.get('headers', [])
                    if h[0].lower() not in (b'cache-control', b'pragma', b'expires')
                ]
                headers.append((b'cache-control', policy))
                message['headers'] = headers
            await send(message)

        await super().__call__(scope, receive, send_wrapper)


ROBOTS_TXT = 'User-agent: *\nDisallow: /\n'


def _register_root_routes(fastapi_app: FastAPI) -> None:
    """Register the two site-root routes that cannot live under ``/static``.

    Extracted from :func:`init` so it can be exercised on a bare app.
    """

    # Keep the app out of search indexes. Some surfaces are readable signed out
    # (the schedule, the bracket views), but "shareable by link" is not "wants
    # to be crawled": indexing would put tournament rosters and results into
    # results pages the community never published, and every crawl writes a
    # page-view telemetry row. robots.txt is per-origin by spec, so this root
    # route covers every tenant path; `BaseLayout` adds a `noindex` meta as the
    # belt to these braces, since robots.txt only asks a crawler not to *fetch*
    # — it does not deindex a URL already known.
    @fastapi_app.get('/robots.txt', include_in_schema=False)
    async def _robots() -> PlainTextResponse:
        return PlainTextResponse(
            ROBOTS_TXT, headers={'Cache-Control': 'public, max-age=3600'},
        )

    # Serve the service worker from the site root: a worker registered under the
    # /static/ path can only control /static/* clients, so it could never take
    # control of the app's start_url ('/'). Root scope is required for install.
    @fastapi_app.get('/sw.js', include_in_schema=False)
    async def _service_worker() -> FileResponse:
        # no-cache so an updated worker is always revalidated — the worker is
        # registered with updateViaCache:'none' (theme/base.py) for the same
        # reason, and a stale SW would pin old behavior for everything it serves.
        return FileResponse(
            'static/sw.js',
            media_type='text/javascript',
            headers={'Cache-Control': 'no-cache'},
        )


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
    logging.getLogger('wizzrobe').info(
        'Tenant routing: PLATFORM_HOST=%s (path mode /t/<slug> + host mode for custom domains)',
        get_platform_host(),
    )

    # Cache policy lives on the class: no-store in dev, stamp-aware in production.
    fastapi_app.mount("/static", VersionedStaticFiles(directory="static"), name="static")

    _register_root_routes(fastapi_app)

    auth.create()
    challonge_oauth.create()
    twitch_oauth.create()
    racetime_oauth.create()
    # Tenant-less like the provider callbacks above: an MCP grant authenticates
    # a person across the platform, not within one community.
    mcp_consent.create()
    # Shared cross-host link handoff routes (/oauth/link/start on the platform
    # host, /oauth/link/claim on custom domains). Registered after the providers
    # so their handoff configs are in the registry; the routes are provider-
    # agnostic and consulted at request time.
    register_link_handoff_pages()
    admin.create()
    home.create()
    volunteer.create()
    # Register the static /equipment/qr-labels route before equipment.create()'s
    # dynamic /equipment/{asset_id} so Starlette matches the labels sheet first.
    equipment_labels.create()
    equipment.create()
    brackets.create()
    # Registered before ui.run_with so the cached, socket-free spectator views
    # sit on the same app (and behind the same tenant middleware) as the pages.
    static_brackets.create()
    platform.create()
    qualifiers.create()
    help_pages.create()
    event_info.create()
    cat_facts.create()
    ui.run_with(
        fastapi_app,
        # mount_path='/gui',  # NOTE this can be omitted if you want the paths passed to @ui.page to be at the root
        title='Wizzrobe',
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
    # Installed on the wrapping app, so it sits *outside* the session middleware
    # ui.run_with just added — that is the only place a Set-Cookie can be taken
    # back off the publicly-cacheable spectator responses.
    fastapi_app.add_middleware(PublicCacheMiddleware)
    register_error_handlers(fastapi_app)