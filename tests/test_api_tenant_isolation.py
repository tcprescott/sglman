"""REST API cross-tenant isolation.

A personal token belongs to exactly one tenant; ``api/dependencies`` sets the
request tenant context from it. These tests prove a token for tenant A sees only
A's data — both through the repository-backed list endpoints and the direct
load-or-404 reads in the action routers.
"""

import pytest

from application.tenant_context import tenant_scope
from models import Match, Role, Tenant, Tournament
from tests.api_helpers import build_api_app, client_for, create_user_token


@pytest.fixture
async def two_tenant_api(db):
    a = await Tenant.get(id=1)
    b = await Tenant.create(name='Beta', slug='beta')

    with tenant_scope(a.id):
        _, token_a = await create_user_token(username='a-staff', roles=[Role.STAFF])
        ta = await Tournament.create(name='A Cup')
        ma = await Match.create(tournament=ta)
    with tenant_scope(b.id):
        _, token_b = await create_user_token(username='b-staff', roles=[Role.STAFF])
        tb = await Tournament.create(name='B Cup')
        mb = await Match.create(tournament=tb)

    return {
        'app': build_api_app(),
        'token_a': token_a, 'token_b': token_b,
        'ta': ta, 'tb': tb, 'ma': ma, 'mb': mb,
    }


async def test_matches_list_is_tenant_isolated(two_tenant_api):
    ctx = two_tenant_api
    async with client_for(ctx['app'], ctx['token_a']) as client:
        r = await client.get('/api/matches')
        assert r.status_code == 200
        assert [m['id'] for m in r.json()] == [ctx['ma'].id]
    async with client_for(ctx['app'], ctx['token_b']) as client:
        r = await client.get('/api/matches')
        assert [m['id'] for m in r.json()] == [ctx['mb'].id]


async def test_cannot_read_other_tenant_match_by_id(two_tenant_api):
    ctx = two_tenant_api
    async with client_for(ctx['app'], ctx['token_a']) as client:
        # A's token requesting B's match by id -> 404 (scoped load).
        r = await client.get(f"/api/matches/{ctx['mb'].id}")
        assert r.status_code == 404
        # A's own match resolves fine.
        r = await client.get(f"/api/matches/{ctx['ma'].id}")
        assert r.status_code == 200


async def test_action_router_load_is_tenant_scoped(two_tenant_api):
    ctx = two_tenant_api
    async with client_for(ctx['app'], ctx['token_a']) as client:
        # Seating B's match with A's staff token -> the load-or-404 helper 404s.
        r = await client.post(f"/api/matches/{ctx['mb'].id}/seat")
        assert r.status_code == 404
