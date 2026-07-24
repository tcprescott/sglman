"""REST API tests for native bracket endpoints (api/routers/brackets.py).

Brackets are tenant-scoped and Staff-gated in-service. Reads use the any-token
dep and stay role-agnostic; writes reject read-only tokens at the HTTP layer and
require Staff in the service. The router is feature-gated by
``FeatureFlag.BRACKETS`` (404 when the tenant lacks it).
"""

import pytest

from application.tenant_context import tenant_scope
from models import BracketFormat, FeatureFlag, Role, TenantFeatureFlag, Tournament
from tests.api_helpers import client_for, create_user_token, enable_all_features


async def _staff_token(username='staff'):
    return await create_user_token(username=username, roles=[Role.STAFF])


async def _tournament(name='Cup'):
    return await Tournament.create(name=name)


# --- Reads / auth matrix --------------------------------------------------


class TestReads:
    async def test_list_unauthenticated(self, db, app):
        async with client_for(app) as c:
            resp = await c.get('/api/brackets?tournament_id=1')
            assert resp.status_code == 401

    async def test_list_role_less_ok(self, db, app):
        """Reads are role-agnostic: a role-less token still gets 200."""
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            await c.post('/api/brackets', json={
                'tournament_id': t.id, 'name': 'Main', 'format': 'single_elim',
            })
        _, plain = await create_user_token(username='plain')
        async with client_for(app, plain) as c:
            resp = await c.get(f'/api/brackets?tournament_id={t.id}')
            assert resp.status_code == 200
            assert [b['name'] for b in resp.json()] == ['Main']

    async def test_get_not_found(self, db, app):
        _, staff = await _staff_token()
        async with client_for(app, staff) as c:
            resp = await c.get('/api/brackets/9999')
            assert resp.status_code == 404


# --- Writes / auth matrix -------------------------------------------------


class TestWrites:
    async def test_create_role_less_forbidden(self, db, app):
        """A non-staff token can read but a write returns 403 (service gate)."""
        t = await _tournament()
        _, plain = await create_user_token(username='plain')
        async with client_for(app, plain) as c:
            resp = await c.post('/api/brackets', json={
                'tournament_id': t.id, 'name': 'X', 'format': 'single_elim',
            })
            assert resp.status_code == 403

    async def test_create_read_only_forbidden(self, db, app):
        """A staff read-only token is rejected on a write by require_write_actor."""
        t = await _tournament()
        _, ro = await create_user_token(username='ro', roles=[Role.STAFF], read_only=True)
        async with client_for(app, ro) as c:
            resp = await c.post('/api/brackets', json={
                'tournament_id': t.id, 'name': 'X', 'format': 'single_elim',
            })
            assert resp.status_code == 403

    async def test_create_bad_format(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            resp = await c.post('/api/brackets', json={
                'tournament_id': t.id, 'name': 'X', 'format': 'nope',
            })
            assert resp.status_code == 422


# --- Happy path -----------------------------------------------------------


class TestHappyPath:
    async def test_create_list_get(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            created = await c.post('/api/brackets', json={
                'tournament_id': t.id, 'name': 'Main', 'format': 'single_elim',
            })
            assert created.status_code == 201
            body = created.json()
            assert body['name'] == 'Main'
            assert body['format'] == 'single_elim'
            assert body['state'] == 'draft'
            bracket_id = body['id']

            listed = await c.get(f'/api/brackets?tournament_id={t.id}')
            assert listed.status_code == 200
            assert [b['id'] for b in listed.json()] == [bracket_id]

            got = await c.get(f'/api/brackets/{bracket_id}')
            assert got.status_code == 200
            assert got.json()['id'] == bracket_id

    async def test_full_flow_report_result(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = (await c.post('/api/brackets', json={
                'tournament_id': t.id, 'name': 'Main', 'format': 'single_elim',
            })).json()['id']

            e1 = (await c.post('/api/brackets/entrants', json={
                'tournament_id': t.id, 'display_name': 'Alice',
            })).json()
            e2 = (await c.post('/api/brackets/entrants', json={
                'tournament_id': t.id, 'display_name': 'Bob',
            })).json()

            entrants = await c.get(f'/api/brackets/entrants?tournament_id={t.id}')
            assert entrants.status_code == 200
            assert {e['display_name'] for e in entrants.json()} == {'Alice', 'Bob'}

            for e in (e1, e2):
                enrolled = await c.post(f'/api/brackets/{bracket_id}/entries', json={
                    'entrant_id': e['id'],
                })
                assert enrolled.status_code == 201

            started = await c.post(f'/api/brackets/{bracket_id}/start')
            assert started.status_code == 200
            assert started.json()['state'] == 'active'

            entries = (await c.get(f'/api/brackets/{bracket_id}/entries')).json()
            entry_by_entrant = {e['entrant_id']: e['id'] for e in entries}

            open_matches = (await c.get(f'/api/brackets/{bracket_id}/open-matches')).json()
            assert len(open_matches) == 1
            match_id = open_matches[0]['id']
            winner_entry_id = entry_by_entrant[e1['id']]

            reported = await c.post(f'/api/brackets/matches/{match_id}/result', json={
                'winner_entry_id': winner_entry_id,
            })
            assert reported.status_code == 200
            assert reported.json()['winner_id'] == winner_entry_id
            assert reported.json()['state'] == 'complete'

            # The final resolving auto-completes the single-elim stage.
            final = await c.get(f'/api/brackets/{bracket_id}')
            assert final.json()['state'] == 'complete'


# --- Feature gate ---------------------------------------------------------


class TestFeatureGate:
    async def test_disabled_feature_404s(self, db, app):
        """With BRACKETS not enabled for the tenant, the router 404s."""
        await TenantFeatureFlag.filter(tenant_id=1, flag=FeatureFlag.BRACKETS.value).update(
            enabled=False,
        )
        _, staff = await _staff_token()
        async with client_for(app, staff) as c:
            resp = await c.get('/api/brackets?tournament_id=1')
            assert resp.status_code == 404


# --- Cross-tenant isolation -----------------------------------------------


class TestTenantIsolation:
    @pytest.fixture
    async def two(self, db, app):
        from models import Tenant

        a = await Tenant.get(id=1)
        b = await Tenant.create(name='Beta', slug='beta')
        with tenant_scope(a.id):
            user_a, _ = await _staff_token('a-staff')
            ta = await _tournament('A Cup')
            bracket_a = await create_bracket_via_service(user_a, ta.id)
        with tenant_scope(b.id):
            await enable_all_features(b.id)
            _, staff_b = await create_user_token(username='b-staff', roles=[Role.STAFF])
        return {'app': app, 'token_b': staff_b, 'bracket_a': bracket_a}

    async def test_get_other_tenant_404(self, two):
        async with client_for(two['app'], two['token_b']) as c:
            resp = await c.get(f"/api/brackets/{two['bracket_a'].id}")
            assert resp.status_code == 404


async def create_bracket_via_service(actor, tournament_id):
    from application.services import BracketService

    return await BracketService().create_bracket(
        actor, tournament_id=tournament_id, name='Main', format=BracketFormat.SINGLE_ELIM,
    )
