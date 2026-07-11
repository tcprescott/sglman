"""Tenant resolution middleware (path mode).

Every tenant is reachable at ``https://<platform>/t/<slug>/…``. This middleware
resolves the slug to a :class:`~models.Tenant`, sets the request-time tenant
context, and **rewrites the ASGI scope** so the app's single set of unprefixed
routes serve the request: ``/t/<slug>`` is stripped from ``scope['path']`` and
appended to ``scope['root_path']``, so downstream routing matches ``/admin`` while
redirects and ``url_for`` built from ``root_path`` keep the ``/t/<slug>`` prefix.

Host-based addressing (a tenant's custom ``domain``) is deferred — the ``domain``
column exists but is not resolved here yet. Requests with no ``/t/`` prefix run
with **no** tenant context: that is the platform surface (landing page,
``/platform``, the shared OAuth callbacks). Tenant pages guard themselves —
``@protected_page`` returns 404 when reached with no tenant.

Transport/API paths (``/_nicegui``, ``/static``, ``/sw.js``, ``/api``) are
tenant-agnostic and skipped: the REST API derives its tenant from the bearer
token, and websocket/asset traffic carries no tenant of its own.

Ordering: added in ``frontend.py`` after ``AuthMiddleware`` so it wraps auth
(Starlette runs last-added outermost) — tenant context and the path rewrite
happen before authentication reads the (already-rewritten) path.
"""

import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from application.services.tenant_service import TenantService
from application.tenant_context import reset_tenant_id, set_tenant_id

# /t/<slug> optionally followed by the rest of the path.
_TENANT_PATH_RE = re.compile(r'^/t/(?P<slug>[a-z0-9][a-z0-9-]*)(?P<rest>/.*)?$')

# Transport / API prefixes that carry no tenant of their own.
_EXCLUDED_PREFIXES = ('/_nicegui', '/static', '/api')
_EXCLUDED_EXACT = ('/sw.js',)


def _is_excluded(path: str) -> bool:
    return path in _EXCLUDED_EXACT or path.startswith(_EXCLUDED_PREFIXES)


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        scope = request.scope
        path = scope.get('path', '/')

        if _is_excluded(path):
            return await call_next(request)

        match = _TENANT_PATH_RE.match(path)
        if match is None:
            # Platform surface (no /t/ prefix): run with no tenant context.
            return await call_next(request)

        slug = match.group('slug')
        tenant = await TenantService.get_by_slug(slug)
        if tenant is None or not tenant.is_active:
            return Response('Tenant not found', status_code=404)

        # Rewrite the scope: strip /t/<slug> into root_path so the unprefixed
        # routes match and url_for/redirects keep the prefix.
        prefix = f'/t/{slug}'
        rest = match.group('rest') or '/'
        scope['path'] = rest
        scope['root_path'] = scope.get('root_path', '') + prefix
        # raw_path drives some routers; keep it consistent with the new path.
        if scope.get('raw_path') is not None:
            query = scope['raw_path'].split(b'?', 1)
            scope['raw_path'] = rest.encode() + (b'?' + query[1] if len(query) > 1 else b'')

        token = set_tenant_id(tenant.id)
        try:
            return await call_next(request)
        finally:
            reset_tenant_id(token)
