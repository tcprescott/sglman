import functools
import inspect
import re
from typing import Iterable, Optional

import sentry_sdk
from fastapi import Request
from nicegui import app, background_tasks, ui
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

from application.services.auth_service import AuthService, get_user_from_discord_id
from application.services.telemetry_service import TelemetryService
from models import Role

# Keep page-view detail bounded: query/path params carry useful engagement
# context (which tab/report), but we cap count and length so a crafted URL
# can't bloat a telemetry row.
_MAX_TRACKED_PARAMS = 15
_MAX_PARAM_LEN = 120


def _record_page_view(path: str, kwargs: dict) -> None:
    """Fire-and-forget a page-view telemetry row for an authenticated load.

    Reads the caller's session identity + browser id here (only valid during
    page building) and hands the write to a background task. Fully defensive:
    telemetry must never interfere with rendering the page.
    """
    try:
        discord_id = app.storage.user.get('discord_id')
        username = app.storage.user.get('username')
        try:
            session_id = app.storage.browser.get('id')
        except Exception:
            session_id = None
        params: dict = {}
        for key, value in kwargs.items():
            if value is None or len(params) >= _MAX_TRACKED_PARAMS:
                continue
            if isinstance(value, (str, int, float, bool)):
                params[key] = str(value)[:_MAX_PARAM_LEN]
        background_tasks.create(
            TelemetryService().track_page_view(
                path=path,
                discord_id=discord_id,
                username=username,
                session_id=session_id,
                params=params or None,
            )
        )
    except Exception:
        pass

# Registry of routes that require authentication; populated by protected_page decorator.
# Plain strings match exactly; entries containing ``{param}`` placeholders are
# compiled to regexes so dynamic NiceGUI routes match incoming request paths.
protected_routes: set[str] = set()


def _matches_protected_route(path: str) -> bool:
    for route in protected_routes:
        if '{' in route:
            pattern = '^' + re.sub(r'\{[^/}]+\}', r'[^/]+', route) + '$'
            if re.match(pattern, path):
                return True
        elif path == route:
            return True
    return False

def protected_page(
    path: str,
    *,
    roles: Optional[Iterable[Role]] = None,
    allow_tournament_membership: bool = False,
    **page_kwargs,
):
    """Register a NiceGUI page that requires authentication and optional roles.

    Args:
        path: Page route.
        roles: If set, the user must hold at least one of these global roles.
        allow_tournament_membership: If True, users who are a Tournament Admin
            or Crew Coordinator of any tournament also pass the role gate.
            Use for pages whose subset of features may be available to per-
            tournament admins (e.g. the admin dashboard shell).
    """
    role_list = list(roles) if roles else None

    gated = role_list is not None or allow_tournament_membership

    def decorator(func):
        protected_routes.add(path)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Capture engagement telemetry for every authenticated page load,
            # gated or not, before any auth short-circuit.
            _record_page_view(path, kwargs)

            if gated:
                user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                allowed = False
                if user is not None and role_list:
                    held = await AuthService.get_roles(user)
                    allowed = bool(held.intersection(role_list))
                if not allowed and allow_tournament_membership:
                    allowed = await AuthService.can_view_admin(user)
                if not allowed:
                    from theme.error_page import render_error_page
                    render_error_page(
                        status_code=403,
                        headline='Forbidden',
                        message='You do not have permission to view this page.',
                        user=user,
                    )
                    return

            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result

        return ui.page(path, **page_kwargs)(wrapper)
    return decorator

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Enforce authentication only for routes that were explicitly marked protected
        if not app.storage.user.get('authenticated', False):
            path = request.url.path
            if not path.startswith('/_nicegui') and _matches_protected_route(path):
                app.storage.user['referrer_path'] = path
                return RedirectResponse('/login')
        else:
            # Attach the logged-in user to Sentry so error events show who hit them.
            sentry_sdk.set_user({
                'id': str(app.storage.user.get('discord_id')),
                'username': app.storage.user.get('username'),
            })
        return await call_next(request)