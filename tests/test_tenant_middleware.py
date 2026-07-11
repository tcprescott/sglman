"""Tenant middleware resolution + ASGI scope-rewrite tests.

Drives the real ``TenantMiddleware`` through a minimal Starlette app (with a real
tenant DB) to confirm ``/t/<slug>`` resolves, sets tenant context, rewrites the
scope so unprefixed routes match, keeps ``root_path`` for link building, 404s
unknown/inactive tenants, and leaves platform + transport paths untouched.
"""

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from application.tenant_context import get_current_tenant_id, reset_tenant_id, set_tenant_id
from middleware.tenant import TenantMiddleware
from models import Tenant


@pytest.fixture(autouse=True)
def _no_ambient_tenant():
    """Override the suite-wide default tenant context so these tests observe the
    middleware's own resolution (platform/api paths must see *no* tenant)."""
    token = set_tenant_id(None)
    try:
        yield
    finally:
        reset_tenant_id(token)


async def _probe(request):
    return JSONResponse({
        'tenant': get_current_tenant_id(),
        'path': request.scope['path'],
        'root_path': request.scope.get('root_path', ''),
    })


def _build_app() -> Starlette:
    app = Starlette(routes=[
        Route('/', _probe),
        Route('/admin', _probe),
        Route('/api/x', _probe),
    ])
    app.add_middleware(TenantMiddleware)
    return app


async def _get(app, path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://platform') as client:
        return await client.get(path)


@pytest.fixture
async def two_tenants(db):
    a = await Tenant.get(id=1)
    a.slug = 'acme'  # rename default -> acme for readability
    await a.save()
    b = await Tenant.create(name='Beta', slug='beta')
    inactive = await Tenant.create(name='Gone', slug='gone', is_active=False)
    return a, b, inactive


async def test_path_mode_resolves_and_rewrites(two_tenants):
    a, _b, _ = two_tenants
    r = await _get(_build_app(), '/t/acme/admin')
    assert r.status_code == 200
    body = r.json()
    assert body['tenant'] == a.id
    assert body['path'] == '/admin'          # prefix stripped for routing
    assert body['root_path'] == '/t/acme'    # prefix preserved for links


async def test_tenant_home_without_trailing_path(two_tenants):
    a, _b, _ = two_tenants
    r = await _get(_build_app(), '/t/acme')
    assert r.status_code == 200
    body = r.json()
    assert body['tenant'] == a.id
    assert body['path'] == '/'


async def test_second_tenant_resolves_independently(two_tenants):
    _a, b, _ = two_tenants
    r = await _get(_build_app(), '/t/beta/admin')
    assert r.json()['tenant'] == b.id


async def test_unknown_slug_404(two_tenants):
    r = await _get(_build_app(), '/t/nope/admin')
    assert r.status_code == 404


async def test_inactive_tenant_404(two_tenants):
    r = await _get(_build_app(), '/t/gone/admin')
    assert r.status_code == 404


async def test_platform_surface_has_no_tenant(two_tenants):
    r = await _get(_build_app(), '/')
    assert r.status_code == 200
    body = r.json()
    assert body['tenant'] is None
    assert body['root_path'] == ''


async def test_api_path_is_excluded(two_tenants):
    r = await _get(_build_app(), '/api/x')
    assert r.status_code == 200
    body = r.json()
    assert body['tenant'] is None          # API derives tenant from its token
    assert body['path'] == '/api/x'        # not rewritten


async def test_context_is_reset_after_request(two_tenants):
    await _get(_build_app(), '/t/acme/admin')
    # The contextvar the middleware set must not leak past the request.
    assert get_current_tenant_id() is None
