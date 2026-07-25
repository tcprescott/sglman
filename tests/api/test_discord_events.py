"""REST API tests for the Discord events endpoints (api/routers/discord_events.py).

Covers the per-tournament settings reads/writes, the mirrored-event link list,
and on-demand reconcile. All operations are service-gated by
``can_manage_sync`` (STAFF / super-admin / ``SYNC_ADMIN``); writes also reject
read-only tokens at the HTTP layer.
"""


from application.services.discord_event_reconciler_service import ReconcileResult
from application.tenant_context import tenant_scope
from models import DiscordScheduledEvent, Role, Tenant, Tournament
from tests.api_helpers import client_for, create_user_token


async def _make_event(**over):
    defaults = dict(
        guild_id=999,
        discord_event_id=555,
        source_type='match',
        source_id=1,
        title='Mirrored Match',
        content_hash='abc123',
    )
    defaults.update(over)
    return await DiscordScheduledEvent.create(**defaults)


class TestReads:
    async def test_list_tournaments_staff_200(self, db, app):
        _, raw = await create_user_token(username='staff', roles=[Role.STAFF])
        await Tournament.create(name='A Cup', discord_events_enabled=True)
        async with client_for(app, raw) as c:
            r = await c.get('/api/discord-events/tournaments')
            assert r.status_code == 200
            names = {t['name'] for t in r.json()}
            assert 'A Cup' in names
            row = next(t for t in r.json() if t['name'] == 'A Cup')
            assert row['discord_events_enabled'] is True
            assert row['discord_event_duration_minutes'] == 60

    async def test_list_tournaments_sync_admin_200(self, db, app):
        """SYNC_ADMIN can manage sync -> 200 (resource-specific extra)."""
        _, raw = await create_user_token(username='syncer', roles=[Role.SYNC_ADMIN])
        await Tournament.create(name='Sync Cup')
        async with client_for(app, raw) as c:
            r = await c.get('/api/discord-events/tournaments')
            assert r.status_code == 200

    async def test_list_events_200(self, db, app):
        _, raw = await create_user_token(username='staff', roles=[Role.STAFF])
        await _make_event()
        async with client_for(app, raw) as c:
            r = await c.get('/api/discord-events/events')
            assert r.status_code == 200
            body = r.json()
            assert len(body) == 1
            assert body[0]['discord_event_id'] == 555
            assert body[0]['source_type'] == 'match'
            assert body[0]['content_hash'] == 'abc123'

    async def test_unauthenticated_401(self, db, app):
        async with client_for(app) as c:
            r = await c.get('/api/discord-events/tournaments')
            assert r.status_code == 401

    async def test_role_less_token_forbidden(self, db, app):
        _, raw = await create_user_token(username='plain')
        async with client_for(app, raw) as c:
            r = await c.get('/api/discord-events/tournaments')
            assert r.status_code == 403


class TestSettingsWrite:
    async def test_patch_updates_settings(self, db, app):
        _, raw = await create_user_token(username='staff', roles=[Role.STAFF])
        t = await Tournament.create(name='Edit Cup')
        async with client_for(app, raw) as c:
            r = await c.patch(
                f'/api/discord-events/tournaments/{t.id}',
                json={'enabled': True, 'duration_minutes': 90, 'title_template': 'Race: {match}'},
            )
            assert r.status_code == 200
        await t.refresh_from_db()
        assert t.discord_events_enabled is True
        assert t.discord_event_duration_minutes == 90
        assert t.discord_event_title_template == 'Race: {match}'

    async def test_patch_read_only_token_forbidden(self, db, app):
        _, raw = await create_user_token(username='staff', roles=[Role.STAFF], read_only=True)
        t = await Tournament.create(name='RO Cup')
        async with client_for(app, raw) as c:
            r = await c.patch(f'/api/discord-events/tournaments/{t.id}', json={'enabled': True})
            assert r.status_code == 403

    async def test_patch_role_less_forbidden(self, db, app):
        _, raw = await create_user_token(username='plain')
        t = await Tournament.create(name='Gated Cup')
        async with client_for(app, raw) as c:
            r = await c.patch(f'/api/discord-events/tournaments/{t.id}', json={'enabled': True})
            assert r.status_code == 403

    async def test_patch_missing_tournament_404(self, db, app):
        _, raw = await create_user_token(username='staff', roles=[Role.STAFF])
        async with client_for(app, raw) as c:
            r = await c.patch('/api/discord-events/tournaments/999999', json={'enabled': True})
            assert r.status_code == 404


class TestReconcile:
    async def test_reconcile_no_guild_400(self, db, app):
        """The default tenant has no linked guild -> service ValueError -> 400."""
        _, raw = await create_user_token(username='staff', roles=[Role.STAFF])
        async with client_for(app, raw) as c:
            r = await c.post('/api/discord-events/reconcile')
            assert r.status_code == 400

    async def test_reconcile_read_only_forbidden(self, db, app):
        _, raw = await create_user_token(username='staff', roles=[Role.STAFF], read_only=True)
        async with client_for(app, raw) as c:
            r = await c.post('/api/discord-events/reconcile')
            assert r.status_code == 403

    async def test_reconcile_happy_200(self, db, app, monkeypatch):
        tenant = await Tenant.get(id=1)
        tenant.discord_guild_id = 424242
        await tenant.save()
        _, raw = await create_user_token(username='staff', roles=[Role.STAFF])

        async def fake_reconcile(self, tenant, *, actor, now=None):
            return ReconcileResult(created=2, updated=1, cancelled=0, unchanged=3, errors=0)

        monkeypatch.setattr(
            'application.services.discord_event_sync_service.DiscordEventReconcilerService.reconcile_tenant',
            fake_reconcile,
        )
        async with client_for(app, raw) as c:
            r = await c.post('/api/discord-events/reconcile')
            assert r.status_code == 200
            assert r.json() == {'created': 2, 'updated': 1, 'cancelled': 0, 'unchanged': 3, 'errors': 0}


class TestTenantIsolation:
    async def test_tenant_isolation(self, db, app):
        a = await Tenant.get(id=1)
        b = await Tenant.create(name='Beta', slug='beta')
        with tenant_scope(a.id):
            ta = await Tournament.create(name='A Cup')
        with tenant_scope(b.id):
            _, token_b = await create_user_token(username='b-staff', roles=[Role.STAFF])
            tb = await Tournament.create(name='B Cup')

        async with client_for(app, token_b) as c:
            r = await c.get('/api/discord-events/tournaments')
            assert r.status_code == 200
            ids = {t['id'] for t in r.json()}
            assert tb.id in ids
            assert ta.id not in ids

            r = await c.patch(f'/api/discord-events/tournaments/{ta.id}', json={'enabled': True})
            assert r.status_code == 404
