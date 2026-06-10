"""Tests for Phase 5 writes: stream rooms, triforce, notifications, config."""

import pytest

from models import Role, StreamRoom, Tournament, TriforceText, User
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


class TestStreamRooms:
    async def test_stream_manager_crud(self, db, app):
        _, raw = await create_user_token(username='sm', roles=[Role.STREAM_MANAGER])
        async with client_for(app, raw) as c:
            created = await c.post('/api/stream-rooms', json={'name': 'Stage X'})
            assert created.status_code == 201
            rid = created.json()['id']

            updated = await c.patch(f'/api/stream-rooms/{rid}', json={'name': 'Stage Y'})
            assert updated.status_code == 200
            assert updated.json()['name'] == 'Stage Y'

            assert (await c.delete(f'/api/stream-rooms/{rid}')).status_code == 204

    async def test_plain_user_forbidden(self, db, app):
        _, raw = await create_user_token(username='plain')
        async with client_for(app, raw) as c:
            assert (await c.post('/api/stream-rooms', json={'name': 'Z'})).status_code == 403


class TestTriforce:
    async def test_submit_and_moderate(self, db, app):
        _, staff_raw = await create_user_token(username='boss', roles=[Role.STAFF])
        player, player_raw = await create_user_token(username='player')
        t = await Tournament.create(name='Cup', is_active=True)

        async with client_for(app, player_raw) as player_c, client_for(app, staff_raw) as staff_c:
            submitted = await player_c.post(
                '/api/triforce-texts', json={'tournament_id': t.id, 'lines': ['HELLO', 'WORLD', '']}
            )
            assert submitted.status_code == 201
            text_id = submitted.json()['id']

            # Player cannot moderate.
            assert (await player_c.post(
                f'/api/triforce-texts/{text_id}/moderate', json={'approved': True}
            )).status_code == 400  # service raises ValueError -> 400

            # Staff approves.
            approved = await staff_c.post(
                f'/api/triforce-texts/{text_id}/moderate', json={'approved': True}
            )
            assert approved.status_code == 200
            assert approved.json()['approved'] is True

    async def test_submit_invalid_lines(self, db, app):
        _, raw = await create_user_token(username='player')
        t = await Tournament.create(name='Cup', is_active=True)
        async with client_for(app, raw) as c:
            # Only 2 lines -> service requires exactly 3 -> 400.
            resp = await c.post('/api/triforce-texts', json={'tournament_id': t.id, 'lines': ['A', 'B']})
            assert resp.status_code == 400


class TestNotifications:
    async def test_upsert_and_list_preference(self, db, app):
        _, raw = await create_user_token(username='player')
        t = await Tournament.create(name='Cup', is_active=True)
        async with client_for(app, raw) as c:
            put = await c.put(
                '/api/notifications/preferences',
                json={'tournament_id': t.id, 'match_notifications': 'all'},
            )
            assert put.status_code == 200
            assert put.json()['match_notifications'] == 'all'

            listed = await c.get('/api/notifications/preferences')
            assert any(p['tournament_id'] == t.id for p in listed.json())


class TestConfig:
    async def test_staff_sets_config(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        async with client_for(app, raw) as c:
            put = await c.put('/api/config/max_concurrent_players', json={'value': '40'})
            assert put.status_code == 200
            assert put.json()['value'] == '40'

    async def test_non_staff_cannot_set_config(self, db, app):
        _, raw = await create_user_token(username='plain')
        async with client_for(app, raw) as c:
            resp = await c.put('/api/config/max_concurrent_players', json={'value': '40'})
            assert resp.status_code == 403
