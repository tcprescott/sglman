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

# A tenant-prefixed *transport* path: /t/<slug> followed by a tenant-agnostic
# asset / websocket / service-worker route. NiceGUI addresses its static files
# and its socket.io endpoint under the page's root_path (/t/<slug>), so the
# browser requests them prefixed; these must be un-prefixed back to the app's
# real routes. ``_nicegui_ws`` is listed before ``_nicegui`` so the alternation
# matches the longer segment.
_TENANT_TRANSPORT_RE = re.compile(
    r'^(?P<prefix>/t/[a-z0-9][a-z0-9-]*)'
    r'(?P<rest>/(?:_nicegui_ws|_nicegui|static)(?:/.*)?|/sw\.js)$'
)

# Transport / API prefixes that carry no tenant of their own.
_EXCLUDED_PREFIXES = ('/_nicegui', '/static', '/api')
_EXCLUDED_EXACT = ('/sw.js',)


def _is_excluded(path: str) -> bool:
    return path in _EXCLUDED_EXACT or path.startswith(_EXCLUDED_PREFIXES)


class TransportPrefixMiddleware:
    """Strip the ``/t/<slug>`` prefix off tenant-agnostic transport paths.

    NiceGUI derives its client asset + websocket URL prefix from the page's
    ``root_path`` (``/t/<slug>`` in path mode), so a tenant page tells the browser
    to load ``/t/<slug>/_nicegui/…`` and open ``/t/<slug>/_nicegui_ws/…``. Those
    resources are shared, served by the app's *unprefixed* routes, so the prefix
    must be removed — with ``root_path`` left empty, exactly like a bare-host
    asset request (a non-empty ``root_path`` makes NiceGUI's static route 404).

    This is a **pure ASGI** middleware, not ``BaseHTTPMiddleware``, so it also
    handles the ``websocket`` scope — ``BaseHTTPMiddleware`` silently passes
    websockets through untouched, which is why the socket.io connection to
    ``/t/<slug>/_nicegui_ws/…`` would otherwise never be stripped and 404. It
    sets no tenant context (assets carry no tenant; the UI's tenant is resolved
    from the per-client stash written at page build).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] in ('http', 'websocket'):
            match = _TENANT_TRANSPORT_RE.match(scope.get('path', ''))
            if match is not None:
                scope = dict(scope)
                scope['path'] = match.group('rest')
                raw = scope.get('raw_path')
                if raw is not None:
                    raw_head, sep, raw_query = raw.partition(b'?')
                    prefix = match.group('prefix').encode()
                    if raw_head.startswith(prefix):
                        raw_head = raw_head[len(prefix):]
                    scope['raw_path'] = raw_head + (sep + raw_query if sep else b'')
        await self.app(scope, receive, send)


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
        # raw_path drives some routers and is the *undecoded* bytes by contract,
        # so strip the /t/<slug> prefix off the original raw bytes rather than
        # re-encoding the already-decoded `rest` (which would drop percent-encoding
        # in the remainder of the path). The slug is [a-z0-9-], never encoded, so
        # the prefix matches the raw bytes verbatim.
        raw = scope.get('raw_path')
        if raw is not None:
            raw_path_part, sep, raw_query = raw.partition(b'?')
            raw_prefix = prefix.encode()
            if raw_path_part.startswith(raw_prefix):
                new_path_part = raw_path_part[len(raw_prefix):] or b'/'
            else:
                new_path_part = rest.encode()
            scope['raw_path'] = new_path_part + (sep + raw_query if sep else b'')

        token = set_tenant_id(tenant.id)
        try:
            return await call_next(request)
        finally:
            reset_tenant_id(token)
