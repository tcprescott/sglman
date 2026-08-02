"""Reschedule request endpoints.

Verifies the routes delegate to ``MatchRescheduleService`` with the token user
as actor, so they inherit its gates: only a match's players may ask, and only
someone who could edit the match may decide.
"""

import random
from datetime import datetime, timedelta, timezone

from models import Match, MatchPlayers, Role, Tournament, User
from tests.api_helpers import build_api_app, client_for, create_user_token


def _soon(hours: int = 6) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


async def _match_with(player: User) -> Match:
    t = await Tournament.create(name='Cup', is_active=True)
    match = await Match.create(
        tournament=t, scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    # Unique per call: a fixed id collides when a test builds two matches.
    other = await User.create(discord_id=random.randint(1, 10 ** 12), username='opponent')
    await MatchPlayers.create(match=match, user=player)
    await MatchPlayers.create(match=match, user=other)
    return match


async def _ask(client, match_id, **overrides):
    payload = {'reason': 'work clash', 'proposed_at': _soon()}
    payload.update(overrides)
    return await client.post(
        f'/api/matches/{match_id}/reschedule-requests', json=payload,
    )


class TestSubmitting:
    async def test_a_player_can_ask(self, db, app):
        player, raw = await create_user_token(username='p1')
        match = await _match_with(player)

        async with client_for(build_api_app(), raw) as client:
            resp = await _ask(client, match.id)

        assert resp.status_code == 201
        assert resp.json()['status'] == 'pending'

    async def test_a_non_player_gets_403(self, db, app):
        _, raw = await create_user_token(username='nosy')
        owner = await User.create(discord_id=777002, username='owner')
        match = await _match_with(owner)

        async with client_for(build_api_app(), raw) as client:
            resp = await _ask(client, match.id)

        assert resp.status_code == 403

    async def test_no_token_gets_401(self, db, app):
        owner = await User.create(discord_id=777003, username='owner')
        match = await _match_with(owner)

        async with client_for(build_api_app()) as client:
            resp = await _ask(client, match.id)

        assert resp.status_code == 401

    async def test_a_read_only_token_gets_403(self, db, app):
        player, raw = await create_user_token(username='p1', read_only=True)
        match = await _match_with(player)

        async with client_for(build_api_app(), raw) as client:
            resp = await _ask(client, match.id)

        assert resp.status_code == 403

    async def test_an_unknown_match_gets_404(self, db, app):
        _, raw = await create_user_token(username='p1')

        async with client_for(build_api_app(), raw) as client:
            resp = await _ask(client, 999999)

        assert resp.status_code == 404

    async def test_a_missing_reason_gets_422(self, db, app):
        player, raw = await create_user_token(username='p1')
        match = await _match_with(player)

        async with client_for(build_api_app(), raw) as client:
            resp = await client.post(
                f'/api/matches/{match.id}/reschedule-requests',
                json={'proposed_at': _soon()},
            )

        assert resp.status_code == 422


class TestDeciding:
    async def test_staff_can_approve_and_the_match_moves(self, db, app):
        player, player_token = await create_user_token(username='p1')
        _, staff_token = await create_user_token(username='boss', roles=[Role.STAFF])
        match = await _match_with(player)
        when = _soon(30)

        api_app = build_api_app()
        async with client_for(api_app, player_token) as client:
            request_id = (await _ask(client, match.id, proposed_at=when)).json()['id']
        async with client_for(api_app, staff_token) as client:
            resp = await client.post(f'/api/reschedule-requests/{request_id}/approve')

        assert resp.status_code == 200
        assert resp.json()['status'] == 'approved'
        await match.refresh_from_db()
        assert match.scheduled_at == datetime.fromisoformat(when)

    async def test_a_player_cannot_approve_their_own(self, db, app):
        player, raw = await create_user_token(username='p1')
        match = await _match_with(player)

        api_app = build_api_app()
        async with client_for(api_app, raw) as client:
            request_id = (await _ask(client, match.id)).json()['id']
            resp = await client.post(f'/api/reschedule-requests/{request_id}/approve')

        assert resp.status_code == 403

    async def test_declining_requires_a_note(self, db, app):
        player, player_token = await create_user_token(username='p1')
        _, staff_token = await create_user_token(username='boss', roles=[Role.STAFF])
        match = await _match_with(player)

        api_app = build_api_app()
        async with client_for(api_app, player_token) as client:
            request_id = (await _ask(client, match.id)).json()['id']
        async with client_for(api_app, staff_token) as client:
            resp = await client.post(
                f'/api/reschedule-requests/{request_id}/decline', json={},
            )

        assert resp.status_code == 422

    async def test_declining_records_the_note(self, db, app):
        player, player_token = await create_user_token(username='p1')
        _, staff_token = await create_user_token(username='boss', roles=[Role.STAFF])
        match = await _match_with(player)

        api_app = build_api_app()
        async with client_for(api_app, player_token) as client:
            request_id = (await _ask(client, match.id)).json()['id']
        async with client_for(api_app, staff_token) as client:
            resp = await client.post(
                f'/api/reschedule-requests/{request_id}/decline',
                json={'note': 'restream is locked in'},
            )

        body = resp.json()
        assert body['status'] == 'declined'
        assert body['decision_note'] == 'restream is locked in'

    async def test_an_unknown_request_gets_404(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])

        async with client_for(build_api_app(), raw) as client:
            resp = await client.post('/api/reschedule-requests/999999/approve')

        assert resp.status_code == 404


class TestReads:
    async def test_mine_returns_only_my_own(self, db, app):
        player, mine_token = await create_user_token(username='p1')
        other, other_token = await create_user_token(username='p2')
        match = await _match_with(player)
        other_match = await _match_with(other)

        api_app = build_api_app()
        async with client_for(api_app, mine_token) as client:
            await _ask(client, match.id)
        async with client_for(api_app, other_token) as client:
            await _ask(client, other_match.id)
            resp = await client.get('/api/reschedule-requests/mine')

        rows = resp.json()
        assert [r['match_id'] for r in rows] == [other_match.id]

    async def test_the_queue_refuses_a_plain_member(self, db, app):
        """The reason text is not schedule data and is nobody else's to read."""
        player, player_token = await create_user_token(username='p1')
        _, nosy_token = await create_user_token(username='nosy')
        match = await _match_with(player)

        api_app = build_api_app()
        async with client_for(api_app, player_token) as client:
            await _ask(client, match.id)
        async with client_for(api_app, nosy_token) as client:
            resp = await client.get('/api/reschedule-requests')

        assert resp.status_code == 403

    async def test_a_match_listing_refuses_an_outsider(self, db, app):
        player, player_token = await create_user_token(username='p1')
        _, nosy_token = await create_user_token(username='nosy')
        match = await _match_with(player)

        api_app = build_api_app()
        async with client_for(api_app, player_token) as client:
            await _ask(client, match.id)
            own = await client.get(f'/api/matches/{match.id}/reschedule-requests')
        async with client_for(api_app, nosy_token) as client:
            resp = await client.get(f'/api/matches/{match.id}/reschedule-requests')

        assert own.status_code == 200
        assert resp.status_code == 403

    async def test_the_queue_lists_pending_requests(self, db, app):
        player, player_token = await create_user_token(username='p1')
        _, staff_token = await create_user_token(username='boss', roles=[Role.STAFF])
        match = await _match_with(player)

        api_app = build_api_app()
        async with client_for(api_app, player_token) as client:
            await _ask(client, match.id)
        async with client_for(api_app, staff_token) as client:
            resp = await client.get('/api/reschedule-requests')

        assert len(resp.json()) == 1


async def test_a_request_is_invisible_across_tenants(two_tenant_api):
    """The sharpest leak point: a forwarded request id from another community."""
    from application.tenant_context import tenant_scope
    from models import MatchRescheduleRequest

    ctx = two_tenant_api
    with tenant_scope(ctx['ma'].tenant_id):
        asker = await User.create(discord_id=777100, username='a-player')
        await MatchPlayers.create(match=ctx['ma'], user=asker)
        request = await MatchRescheduleRequest.create(
            match=ctx['ma'], requested_by=asker, reason='clash',
        )

    async with client_for(ctx['app'], ctx['token_b']) as client:
        resp = await client.post(f'/api/reschedule-requests/{request.id}/approve')
        listed = await client.get('/api/reschedule-requests')

    assert resp.status_code == 404
    assert listed.json() == []
