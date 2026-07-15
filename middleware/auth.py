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
from application.services.feature_flag_service import FeatureFlagService
from application.services.telemetry_service import TelemetryService
from application.tenant_context import get_current_tenant_id, stash_client_tenant_id, tenant_scope
from models import FeatureFlag, Role


async def _run_in_tenant(tenant_id, coro) -> None:
    """Await a deferred (background-task) coroutine with a tenant bound.

    Page-view telemetry is captured in a background task, which runs outside the
    request and so loses the contextvar — capture the tenant at page-build time
    and rebind it here so the row is tenant-stamped."""
    with tenant_scope(tenant_id):
        await coro

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
        tenant_id = get_current_tenant_id()
        background_tasks.create(
            _run_in_tenant(
                tenant_id,
                TelemetryService().track_page_view(
                    path=path,
                    discord_id=discord_id,
                    username=username,
                    session_id=session_id,
                    params=params or None,
                ),
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
    feature: Optional[FeatureFlag] = None,
    telemetry_path: Optional[str] = None,
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
        feature: If set, the page is gated behind a per-tenant feature flag —
            when the flag is not live for the current tenant the page 404s
            (hidden, like an unknown route), independent of the user's roles.
        telemetry_path: Page-view path recorded for engagement telemetry. Lets
            sibling routes that render the same page (e.g. ``/admin`` and
            ``/admin/{section}``) report under one stable path.
    """
    role_list = list(roles) if roles else None
    view_path = telemetry_path or path

    gated = role_list is not None or allow_tournament_membership

    def decorator(func):
        protected_routes.add(path)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Capture engagement telemetry for every authenticated page load,
            # gated or not, before any auth short-circuit.
            _record_page_view(view_path, kwargs)

            # Every @protected_page is a tenant page. If reached with no tenant
            # (a bare /admin on the platform host, not /t/<slug>/admin), 404.
            tid = get_current_tenant_id()
            if tid is None:
                from theme.error_page import render_error_page
                render_error_page(
                    status_code=404,
                    headline='Not Found',
                    message='This page is only available within a community (/t/<slug>/…).',
                    user=None,
                )
                return
            # Stash the tenant onto the connection so websocket UI event handlers
            # (which run outside any request) can resolve it via the fallback.
            stash_client_tenant_id(tid)

            # Feature gate (before the role gate): a subsystem the tenant hasn't
            # enabled is hidden from everyone — 404, like an unknown route — so a
            # not-yet-released feature never leaks and role has no bearing.
            if feature is not None and not await FeatureFlagService().is_enabled(feature):
                from theme.error_page import render_error_page
                render_error_page(
                    status_code=404,
                    headline='Not Found',
                    message='This feature is not enabled for this community.',
                    user=None,
                )
                return

            # Authorization for a *gated* page comes from the user's tenant-scoped
            # roles / tournament-admin membership / super-admin — all evaluated in
            # this tenant's context, so a role in another tenant grants nothing
            # here. Role-less protected pages need only authentication (which
            # AuthMiddleware already enforced), matching pre-multitenancy access;
            # there is no separate "must be a member" gate, since the app has no
            # self-serve/invite enrollment path and it would lock out new users.
            if gated:
                user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                allowed = await AuthService.is_super_admin(user)
                if not allowed and user is not None and role_list:
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


def protected_tab_page(base: str, **kwargs):
    """Register a tabbed hub page under both ``base`` and ``base/{section}``.

    The section slug lives in the path (``/admin/schedule``) rather than a query
    param; both routes render the same page function, which reads the ``section``
    slug and resolves it to the active tab. Two ``protected_page`` calls (rather
    than stacked decorators, which return the ``ui.page`` object, not the
    function) with a shared ``telemetry_path`` so both report under ``base``.
    """
    def deco(func):
        protected_page(base, telemetry_path=base, **kwargs)(func)
        protected_page(f'{base}/{{section}}', telemetry_path=base, **kwargs)(func)
        return func
    return deco


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Enforce authentication only for routes that were explicitly marked protected
        if not app.storage.user.get('authenticated', False):
            # Under path mode TenantMiddleware has already stripped /t/<slug> into
            # root_path, so request.url.path is the unprefixed route; rebuild the
            # tenant-qualified referrer and /login target from root_path so a
            # path-mode login round-trips back to /t/<slug>/….
            path = request.url.path
            root_path = request.scope.get('root_path', '')
            if not path.startswith('/_nicegui') and _matches_protected_route(path):
                app.storage.user['referrer_path'] = f'{root_path}{path}'
                return RedirectResponse(f'{root_path}/login')
        else:
            # Attach the logged-in user to Sentry so error events show who hit them.
            sentry_sdk.set_user({
                'id': str(app.storage.user.get('discord_id')),
                'username': app.storage.user.get('username'),
            })
        return await call_next(request)