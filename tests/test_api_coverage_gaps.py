"""Tests for the newly exposed REST endpoints:

- Match watchers (watch / unwatch / list watched)
- Player self-service availability
- Match-time suggestion
- Discord role mappings (Staff)
"""

from datetime import timedelta

import pytest

from application.utils.timezone import now_eastern
from models import Match, Role, SystemConfiguration, Tournament, User
from tests.api_helpers import build_api_app, client_for, create_user_token


@pytest.fixture(autouse=True)
def stub_discord_queue(monkeypatch):
    captured = []
    monkeypatch.setattr('application.services.discord_queue.enqueue', captured.append)
    yield captured
    for coro in captured:
        coro.close()


@pytest.fixture
def app():
    return build_api_app()


# ---------------------------------------------------------------------------
# Match watchers
# ---------------------------------------------------------------------------


class TestMatchWatchers:
    async def test_watch_list_and_unwatch(self, db, app):
        _, raw = await create_user_token(username='fan')
        t = await Tournament.create(name='Cup', is_active=True)
        match = await Match.create(tournament=t)
        async with client_for(app, raw) as c:
            assert (await c.get('/api/matches/watching')).json() == []

            watched = await c.post(f'/api/matches/{match.id}/watch')
            assert watched.status_code == 200

            listed = await c.get('/api/matches/watching')
            assert [m['id'] for m in listed.json()] == [match.id]

            removed = await c.delete(f'/api/matches/{match.id}/watch')
            assert removed.status_code == 204
            assert (await c.get('/api/matches/watching')).json() == []

    async def test_watch_missing_match_is_400(self, db, app):
        _, raw = await create_user_token(username='fan')
        async with client_for(app, raw) as c:
            assert (await c.post('/api/matches/999/watch')).status_code == 400

    async def test_read_only_token_cannot_watch(self, db, app):
        _, raw = await create_user_token(username='fan', read_only=True)
        t = await Tournament.create(name='Cup', is_active=True)
        match = await Match.create(tournament=t)
        async with client_for(app, raw) as c:
            assert (await c.post(f'/api/matches/{match.id}/watch')).status_code == 403


# ---------------------------------------------------------------------------
# Player availability
# ---------------------------------------------------------------------------


class TestPlayerAvailability:
    async def test_set_list_and_clear(self, db, app):
        _, raw = await create_user_token(username='player')
        windows = {
            'windows': [
                {
                    'starts_at': '2026-06-10T18:00:00+00:00',
                    'ends_at': '2026-06-10T20:00:00+00:00',
                    'status': 'preferred',
                    'note': 'evenings',
                }
            ]
        }
        async with client_for(app, raw) as c:
            put = await c.put('/api/users/me/availability', json=windows)
            assert put.status_code == 200
            assert len(put.json()) == 1
            assert put.json()[0]['status'] == 'preferred'

            listed = await c.get('/api/users/me/availability')
            assert len(listed.json()) == 1

            assert (await c.delete('/api/users/me/availability')).status_code == 204
            assert (await c.get('/api/users/me/availability')).json() == []

    async def test_inverted_window_is_400(self, db, app):
        _, raw = await create_user_token(username='player')
        bad = {
            'windows': [
                {
                    'starts_at': '2026-06-10T20:00:00+00:00',
                    'ends_at': '2026-06-10T18:00:00+00:00',
                }
            ]
        }
        async with client_for(app, raw) as c:
            assert (await c.put('/api/users/me/availability', json=bad)).status_code == 400

    async def test_read_only_token_cannot_set(self, db, app):
        _, raw = await create_user_token(username='player', read_only=True)
        async with client_for(app, raw) as c:
            resp = await c.put('/api/users/me/availability', json={'windows': []})
            assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Match-time suggestion
# ---------------------------------------------------------------------------


class TestMatchSuggestion:
    async def test_suggests_a_time(self, db, app):
        _, raw = await create_user_token(username='ta')
        today = now_eastern().date()
        await SystemConfiguration.create(name='event_start_date', value=today.isoformat())
        await SystemConfiguration.create(
            name='event_end_date', value=(today + timedelta(days=2)).isoformat(),
        )
        t = await Tournament.create(name='Cup', is_active=True, average_match_duration=60)
        p1 = await User.create(discord_id=201, username='p1')
        p2 = await User.create(discord_id=202, username='p2')
        async with client_for(app, raw) as c:
            resp = await c.get(
                f'/api/tournaments/{t.id}/match-suggestion',
                params=[('player_ids', p1.id), ('player_ids', p2.id)],
            )
            assert resp.status_code == 200
            assert 'suggested_at' in resp.json()


# ---------------------------------------------------------------------------
# Discord role mappings
# ---------------------------------------------------------------------------


class TestDiscordRoleMappings:
    async def test_staff_crud(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        async with client_for(app, raw) as c:
            created = await c.post(
                '/api/discord-role-mappings',
                json={
                    'guild_id': 1,
                    'discord_role_id': 2,
                    'discord_role_name': 'Staff',
                    'app_role': Role.STAFF.value,
                },
            )
            assert created.status_code == 201
            mapping_id = created.json()['id']

            listed = await c.get('/api/discord-role-mappings')
            assert any(m['id'] == mapping_id for m in listed.json())

            assert (await c.delete(f'/api/discord-role-mappings/{mapping_id}')).status_code == 204

    async def test_non_staff_forbidden(self, db, app):
        _, raw = await create_user_token(username='nobody')
        async with client_for(app, raw) as c:
            assert (await c.get('/api/discord-role-mappings')).status_code == 403
