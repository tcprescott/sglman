"""REST API tests for the async-qualifier endpoints (api/routers/async_qualifiers.py).

Covers the admin management surface (gated by ``can_admin_qualifier``), the player
run lifecycle (start → submit on your own run), review (self-review blocked), the
open/public reads, the while-open leaderboard lockdown, and cross-tenant isolation.
"""

from datetime import datetime, timedelta, timezone

import pytest

from application.tenant_context import tenant_scope
from models import AsyncQualifier, Role, Tenant, User
from tests.api_helpers import build_api_app, client_for, create_user_token, enable_all_features

UTC = timezone.utc


def past_iso():
    return (datetime.now(UTC) - timedelta(days=1)).isoformat()


def future_iso():
    return (datetime.now(UTC) + timedelta(days=1)).isoformat()


async def _admin_token(username='qadmin', read_only=False):
    return await create_user_token(username=username, roles=[Role.QUALIFIER_ADMIN], read_only=read_only)


async def _open_qualifier(client, name='Open Cup'):
    resp = await client.post('/api/async-qualifiers', json={
        'name': name,
        'opens_at': past_iso(),
        'closes_at': future_iso(),
    })
    assert resp.status_code == 201, resp.text
    return resp.json()['id']


async def _pool_with_permalink(client, qualifier_id, pool_name='Pool A'):
    pool_resp = await client.post(f'/api/async-qualifiers/{qualifier_id}/pools', json={'name': pool_name})
    assert pool_resp.status_code == 201, pool_resp.text
    pool_id = pool_resp.json()['id']
    pl_resp = await client.post(
        f'/api/async-qualifiers/pools/{pool_id}/permalinks',
        json={'url': 'https://example.com/seed-1'},
    )
    assert pl_resp.status_code == 201, pl_resp.text
    return pool_id


# --- baseline auth --------------------------------------------------------

class TestBaseline:
    async def test_list_qualifiers_admin_ok(self, db, app):
        _, raw = await _admin_token()
        async with client_for(app, raw) as c:
            await _open_qualifier(c, name='Alpha')
            resp = await c.get('/api/async-qualifiers')
            assert resp.status_code == 200
            assert 'Alpha' in {q['name'] for q in resp.json()}

    async def test_unauthenticated_is_401(self, db, app):
        async with client_for(app) as c:
            resp = await c.get('/api/async-qualifiers')
            assert resp.status_code == 401

    async def test_read_only_token_forbidden_on_write(self, db, app):
        _, raw = await _admin_token(read_only=True)
        async with client_for(app, raw) as c:
            resp = await c.post('/api/async-qualifiers', json={'name': 'Nope'})
            assert resp.status_code == 403

    async def test_role_less_token_forbidden_on_gated_read(self, db, app):
        _, raw = await create_user_token(username='plain')
        async with client_for(app, raw) as c:
            resp = await c.get('/api/async-qualifiers')
            assert resp.status_code == 403

    async def test_role_less_token_forbidden_on_create(self, db, app):
        _, raw = await create_user_token(username='plain')
        async with client_for(app, raw) as c:
            resp = await c.post('/api/async-qualifiers', json={'name': 'X'})
            assert resp.status_code == 403


# --- admin management (QUALIFIER_ADMIN, not STAFF) ------------------------

class TestAdminManagement:
    async def test_qualifier_admin_can_create_and_get(self, db, app):
        _, raw = await _admin_token()
        async with client_for(app, raw) as c:
            create = await c.post('/api/async-qualifiers', json={
                'name': 'Season 1', 'runs_per_pool': 2, 'allowed_reattempts': 1,
            })
            assert create.status_code == 201
            qid = create.json()['id']
            assert create.json()['runs_per_pool'] == 2

            got = await c.get(f'/api/async-qualifiers/{qid}')
            assert got.status_code == 200
            assert got.json()['name'] == 'Season 1'

    async def test_update_qualifier(self, db, app):
        _, raw = await _admin_token()
        async with client_for(app, raw) as c:
            qid = await _open_qualifier(c, name='Rename Me')
            resp = await c.patch(f'/api/async-qualifiers/{qid}', json={'name': 'Renamed'})
            assert resp.status_code == 200
            assert resp.json()['name'] == 'Renamed'

    async def test_update_qualifier_not_found(self, db, app):
        _, raw = await _admin_token()
        async with client_for(app, raw) as c:
            resp = await c.patch('/api/async-qualifiers/999999', json={'name': 'X'})
            assert resp.status_code == 404

    async def test_delete_qualifier(self, db, app):
        _, raw = await _admin_token()
        async with client_for(app, raw) as c:
            qid = await _open_qualifier(c, name='Temp')
            resp = await c.delete(f'/api/async-qualifiers/{qid}')
            assert resp.status_code == 204
            assert await AsyncQualifier.get_or_none(id=qid) is None

    async def test_add_and_remove_admin(self, db, app):
        _, raw = await _admin_token()
        target = await User.create(discord_id=778899, username='reviewer')
        async with client_for(app, raw) as c:
            qid = await _open_qualifier(c, name='With Admins')
            add = await c.post(f'/api/async-qualifiers/{qid}/admins', json={'user_id': target.id})
            assert add.status_code == 201
            listed = await c.get(f'/api/async-qualifiers/{qid}/admins')
            assert target.id in {u['id'] for u in listed.json()}
            remove = await c.delete(f'/api/async-qualifiers/{qid}/admins/{target.id}')
            assert remove.status_code == 204

    async def test_add_admin_unknown_user_404(self, db, app):
        _, raw = await _admin_token()
        async with client_for(app, raw) as c:
            qid = await _open_qualifier(c)
            resp = await c.post(f'/api/async-qualifiers/{qid}/admins', json={'user_id': 999999})
            assert resp.status_code == 404

    async def test_pool_and_permalink_crud(self, db, app):
        _, raw = await _admin_token()
        async with client_for(app, raw) as c:
            qid = await _open_qualifier(c)
            pool = await c.post(f'/api/async-qualifiers/{qid}/pools', json={'name': 'Main'})
            assert pool.status_code == 201
            pool_id = pool.json()['id']

            pools = await c.get(f'/api/async-qualifiers/{qid}/pools')
            assert [p['id'] for p in pools.json()] == [pool_id]

            patched = await c.patch(f'/api/async-qualifiers/pools/{pool_id}', json={'name': 'Renamed Pool'})
            assert patched.status_code == 200
            assert patched.json()['name'] == 'Renamed Pool'

            pl = await c.post(
                f'/api/async-qualifiers/pools/{pool_id}/permalinks',
                json={'url': 'https://example.com/s1', 'live_race': False},
            )
            assert pl.status_code == 201
            permalink_id = pl.json()['id']
            assert pl.json()['url'] == 'https://example.com/s1'

            bulk = await c.post(
                f'/api/async-qualifiers/pools/{pool_id}/permalinks/bulk',
                json={'urls': ['https://example.com/a', '', 'https://example.com/b']},
            )
            assert bulk.status_code == 201
            assert len(bulk.json()) == 2

            upd = await c.patch(
                f'/api/async-qualifiers/permalinks/{permalink_id}', json={'notes': 'seeded'},
            )
            assert upd.status_code == 200
            assert upd.json()['notes'] == 'seeded'

            deleted = await c.delete(f'/api/async-qualifiers/permalinks/{permalink_id}')
            assert deleted.status_code == 204

            deleted_pool = await c.delete(f'/api/async-qualifiers/pools/{pool_id}')
            assert deleted_pool.status_code == 204


# --- open / public reads --------------------------------------------------

class TestPublicReads:
    async def test_open_route_precedes_id_and_lists_active(self, db, app):
        _, raw = await _admin_token()
        async with client_for(app, raw) as c:
            await _open_qualifier(c, name='Live One')
            resp = await c.get('/api/async-qualifiers/open')
            assert resp.status_code == 200
            assert 'Live One' in {q['name'] for q in resp.json()}

    async def test_public_shell_ungated(self, db, app):
        _, admin_raw = await _admin_token()
        async with client_for(app, admin_raw) as c:
            qid = await _open_qualifier(c, name='Public Shell')
        _, plain_raw = await create_user_token(username='player')
        async with client_for(app, plain_raw) as c:
            resp = await c.get(f'/api/async-qualifiers/{qid}/public')
            assert resp.status_code == 200
            assert resp.json()['name'] == 'Public Shell'

    async def test_ungated_reads_omit_internal_config(self, db, app):
        # ``config`` holds internal draw-fairness / par-scoring knobs and messaging
        # templates. The admin-gated GET exposes it; the two ungated player-facing
        # surfaces (/{id}/public and /open) must NOT leak it.
        _, admin_raw = await _admin_token()
        async with client_for(app, admin_raw) as c:
            qid = await _open_qualifier(c, name='Config Guard')
            admin_get = await c.get(f'/api/async-qualifiers/{qid}')
            assert admin_get.status_code == 200
            assert 'config' in admin_get.json()
        _, plain_raw = await create_user_token(username='config-peeker')
        async with client_for(app, plain_raw) as c:
            pub = await c.get(f'/api/async-qualifiers/{qid}/public')
            assert pub.status_code == 200
            assert pub.json()['name'] == 'Config Guard'
            assert 'config' not in pub.json()

            open_list = await c.get('/api/async-qualifiers/open')
            assert open_list.status_code == 200
            rows = [q for q in open_list.json() if q['id'] == qid]
            assert rows and 'config' not in rows[0]


# --- player run lifecycle + review ---------------------------------------

class TestRunLifecycle:
    async def test_start_then_submit_own_run(self, db, app):
        _, raw = await _admin_token()
        async with client_for(app, raw) as c:
            qid = await _open_qualifier(c)
            pool_id = await _pool_with_permalink(c, qid)

            start = await c.post(f'/api/async-qualifiers/{qid}/runs', json={'pool_id': pool_id})
            assert start.status_code == 201, start.text
            run_id = start.json()['id']
            assert start.json()['status'] == 'in_progress'

            active = await c.get(f'/api/async-qualifiers/{qid}/me/active-run')
            assert active.status_code == 200
            assert active.json()['id'] == run_id

            submit = await c.post(
                f'/api/async-qualifiers/runs/{run_id}/submit', json={'elapsed_seconds': 1200},
            )
            assert submit.status_code == 200, submit.text
            assert submit.json()['status'] == 'finished'
            assert submit.json()['review_status'] == 'pending'

            my_runs = await c.get(f'/api/async-qualifiers/{qid}/me/runs')
            assert run_id in {r['id'] for r in my_runs.json()}

    async def test_self_review_blocked(self, db, app):
        _, raw = await _admin_token()
        async with client_for(app, raw) as c:
            qid = await _open_qualifier(c)
            pool_id = await _pool_with_permalink(c, qid)
            start = await c.post(f'/api/async-qualifiers/{qid}/runs', json={'pool_id': pool_id})
            run_id = start.json()['id']
            await c.post(f'/api/async-qualifiers/runs/{run_id}/submit', json={'elapsed_seconds': 900})

            review = await c.post(
                f'/api/async-qualifiers/runs/{run_id}/review', json={'approved': True},
            )
            assert review.status_code == 400
            assert 'own run' in review.json()['detail'].lower()

    async def test_review_queue_forbidden_for_non_admin(self, db, app):
        _, admin_raw = await _admin_token()
        async with client_for(app, admin_raw) as c:
            qid = await _open_qualifier(c)
        _, plain_raw = await create_user_token(username='plain')
        async with client_for(app, plain_raw) as c:
            resp = await c.get(f'/api/async-qualifiers/{qid}/review-queue')
            assert resp.status_code == 403

    async def test_review_queue_ok_for_admin(self, db, app):
        _, raw = await _admin_token()
        async with client_for(app, raw) as c:
            qid = await _open_qualifier(c)
            resp = await c.get(f'/api/async-qualifiers/{qid}/review-queue')
            assert resp.status_code == 200
            assert resp.json() == []


# --- leaderboard lockdown -------------------------------------------------

class TestLeaderboard:
    async def test_hidden_while_open_for_non_admin(self, db, app):
        _, admin_raw = await _admin_token()
        async with client_for(app, admin_raw) as c:
            qid = await _open_qualifier(c, name='Locked')
            # Admin can see it even while open.
            admin_board = await c.get(f'/api/async-qualifiers/{qid}/leaderboard')
            assert admin_board.status_code == 200
        _, plain_raw = await create_user_token(username='peeker')
        async with client_for(app, plain_raw) as c:
            resp = await c.get(f'/api/async-qualifiers/{qid}/leaderboard')
            assert resp.status_code == 403


# --- cross-tenant isolation ----------------------------------------------

class TestTenantIsolation:
    @pytest.fixture
    async def two_tenants(self, db):
        a = await Tenant.get(id=1)
        b = await Tenant.create(name='Beta', slug='beta')
        with tenant_scope(a.id):
            qa = await AsyncQualifier.create(name='A Cup', is_active=True)
        with tenant_scope(b.id):
            await enable_all_features(b.id)
            _, token_b = await create_user_token(username='b-admin', roles=[Role.QUALIFIER_ADMIN])
        return {'app': build_api_app(), 'token_b': token_b, 'qa': qa}

    async def test_other_tenant_qualifier_is_404(self, two_tenants):
        ctx = two_tenants
        async with client_for(ctx['app'], ctx['token_b']) as c:
            resp = await c.get(f"/api/async-qualifiers/{ctx['qa'].id}")
            assert resp.status_code == 404

    async def test_list_omits_other_tenant_row(self, two_tenants):
        ctx = two_tenants
        async with client_for(ctx['app'], ctx['token_b']) as c:
            resp = await c.get('/api/async-qualifiers')
            assert resp.status_code == 200
            assert ctx['qa'].id not in {q['id'] for q in resp.json()}
