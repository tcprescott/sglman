"""Tests for the Phase 2 read endpoints across all domains."""

from datetime import datetime, timezone

import pytest

from models import (
    AuditLog,
    Match,
    Role,
    StreamRoom,
    SystemConfiguration,
    Tournament,
    TriforceText,
    User,
)
from tests.api_helpers import build_api_app, client_for, create_user_token


@pytest.fixture
def app():
    return build_api_app()


# ---------------------------------------------------------------------------
# Tournaments / stream rooms — any authenticated user
# ---------------------------------------------------------------------------


class TestTournamentsAndRooms:
    async def test_list_and_get_tournament(self, db, app):
        _, raw = await create_user_token()
        t = await Tournament.create(name='Cup A')
        async with client_for(app, raw) as c:
            listed = await c.get('/api/tournaments')
            assert listed.status_code == 200
            assert any(item['id'] == t.id for item in listed.json())

            detail = await c.get(f'/api/tournaments/{t.id}')
            assert detail.status_code == 200
            assert detail.json()['name'] == 'Cup A'

    async def test_get_missing_tournament_is_404(self, db, app):
        _, raw = await create_user_token()
        async with client_for(app, raw) as c:
            assert (await c.get('/api/tournaments/999')).status_code == 404

    async def test_list_stream_rooms(self, db, app):
        _, raw = await create_user_token()
        await StreamRoom.create(name='Stage 1')
        async with client_for(app, raw) as c:
            resp = await c.get('/api/stream-rooms')
            assert resp.status_code == 200
            assert resp.json()[0]['name'] == 'Stage 1'


# ---------------------------------------------------------------------------
# Users — staff gated, plus self access
# ---------------------------------------------------------------------------


class TestUsers:
    async def test_me_returns_self_with_roles(self, db, app):
        _, raw = await create_user_token(username='self', roles=[Role.STAFF])
        async with client_for(app, raw) as c:
            resp = await c.get('/api/users/me')
            assert resp.status_code == 200
            body = resp.json()
            assert body['username'] == 'self'
            assert 'staff' in body['roles']

    async def test_list_users_requires_staff(self, db, app):
        _, raw = await create_user_token(username='plain')
        async with client_for(app, raw) as c:
            assert (await c.get('/api/users')).status_code == 403

    async def test_staff_can_list_users(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        await User.create(discord_id=555, username='someone')
        async with client_for(app, raw) as c:
            resp = await c.get('/api/users')
            assert resp.status_code == 200
            assert any(u['username'] == 'someone' for u in resp.json())

    async def test_non_staff_cannot_read_other_user(self, db, app):
        _, raw = await create_user_token(username='nosy')
        other = await User.create(discord_id=777, username='target')
        async with client_for(app, raw) as c:
            assert (await c.get(f'/api/users/{other.id}')).status_code == 403


# ---------------------------------------------------------------------------
# Audit — admin gated
# ---------------------------------------------------------------------------


class TestAudit:
    async def test_audit_requires_admin(self, db, app):
        _, raw = await create_user_token(username='plain')
        async with client_for(app, raw) as c:
            assert (await c.get('/api/audit-logs')).status_code == 403

    async def test_staff_reads_audit_page(self, db, app):
        user, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        await AuditLog.create(user=user, action='match.created', details='{"match_id": 1}')
        async with client_for(app, raw) as c:
            resp = await c.get('/api/audit-logs')
            assert resp.status_code == 200
            body = resp.json()
            assert body['total'] >= 1
            entry = next(e for e in body['items'] if e['action'] == 'match.created')
            assert entry['details'] == {'match_id': 1}


# ---------------------------------------------------------------------------
# System config — staff gated
# ---------------------------------------------------------------------------


class TestConfig:
    async def test_config_requires_staff(self, db, app):
        _, raw = await create_user_token(username='plain')
        async with client_for(app, raw) as c:
            assert (await c.get('/api/config')).status_code == 403

    async def test_staff_reads_config(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        await SystemConfiguration.create(name='event_start_date', value='2026-06-01')
        async with client_for(app, raw) as c:
            resp = await c.get('/api/config/event_start_date')
            assert resp.status_code == 200
            assert resp.json()['value'] == '2026-06-01'


# ---------------------------------------------------------------------------
# Triforce texts — own vs moderation
# ---------------------------------------------------------------------------


class TestTriforce:
    async def test_own_submissions(self, db, app):
        user, raw = await create_user_token(username='player')
        t = await Tournament.create(name='Cup', is_active=True)
        await TriforceText.create(tournament=t, user=user, text='HELLO', author='player')
        async with client_for(app, raw) as c:
            resp = await c.get(f'/api/triforce-texts/mine?tournament_id={t.id}')
            assert resp.status_code == 200
            assert len(resp.json()) == 1

    async def test_moderation_requires_permission(self, db, app):
        _, raw = await create_user_token(username='player')
        t = await Tournament.create(name='Cup', is_active=True)
        async with client_for(app, raw) as c:
            resp = await c.get(f'/api/triforce-texts?tournament_id={t.id}')
            assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Match detail
# ---------------------------------------------------------------------------


class TestMatchDetail:
    async def test_get_match_detail(self, db, app):
        _, raw = await create_user_token()
        t = await Tournament.create(name='T')
        m = await Match.create(
            tournament=t, scheduled_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        async with client_for(app, raw) as c:
            resp = await c.get(f'/api/matches/{m.id}')
            assert resp.status_code == 200
            assert resp.json()['id'] == m.id

    async def test_missing_match_is_404(self, db, app):
        _, raw = await create_user_token()
        async with client_for(app, raw) as c:
            assert (await c.get('/api/matches/4242')).status_code == 404
