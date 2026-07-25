"""Tests for Phase 3 match & crew write endpoints.

Verifies that endpoints route through the service layer with the token user as
actor, inheriting its permission checks (Staff/TA gates, read-only rejection).
"""


from models import Commentator, MatchPlayers, Role, Tournament, User
from tests.api_helpers import client_for, create_user_token


async def _tournament_and_players():
    t = await Tournament.create(name='Cup', is_active=True)
    p1 = await User.create(discord_id=101, username='p1')
    p2 = await User.create(discord_id=102, username='p2')
    return t, p1, p2


async def _create_match(client, t, p1, p2, **overrides):
    payload = {
        'tournament_id': t.id,
        'scheduled_date': '2026-06-10',
        'scheduled_time': '18:00',
        'player_ids': [p1.id, p2.id],
    }
    payload.update(overrides)
    return await client.post('/api/matches', json=payload)


class TestCreateMatch:
    async def test_staff_can_create(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        t, p1, p2 = await _tournament_and_players()
        async with client_for(app, raw) as c:
            resp = await _create_match(c, t, p1, p2)
            assert resp.status_code == 201
            body = resp.json()
            assert len(body['players']) == 2

    async def test_non_staff_is_forbidden(self, db, app):
        _, raw = await create_user_token(username='nobody')
        t, p1, p2 = await _tournament_and_players()
        async with client_for(app, raw) as c:
            resp = await _create_match(c, t, p1, p2)
            assert resp.status_code == 403

    async def test_read_only_token_is_forbidden(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF], read_only=True)
        t, p1, p2 = await _tournament_and_players()
        async with client_for(app, raw) as c:
            resp = await _create_match(c, t, p1, p2)
            assert resp.status_code == 403


class TestLifecycle:
    async def test_seat_start_finish_confirm(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        t, p1, p2 = await _tournament_and_players()
        async with client_for(app, raw) as c:
            mid = (await _create_match(c, t, p1, p2)).json()['id']

            seated = await c.post(f'/api/matches/{mid}/seat')
            assert seated.status_code == 200
            assert seated.json()['seated_at'] is not None

            assert (await c.post(f'/api/matches/{mid}/start')).status_code == 200
            finished = await c.post(f'/api/matches/{mid}/finish')
            assert finished.status_code == 200
            assert finished.json()['finished_at'] is not None
            assert (await c.post(f'/api/matches/{mid}/confirm')).status_code == 200

    async def test_finish_before_start_is_400(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        t, p1, p2 = await _tournament_and_players()
        async with client_for(app, raw) as c:
            mid = (await _create_match(c, t, p1, p2)).json()['id']
            # Must be seated+started first; finishing immediately is a 400.
            assert (await c.post(f'/api/matches/{mid}/finish')).status_code == 400

    async def test_record_result(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        t, p1, p2 = await _tournament_and_players()
        async with client_for(app, raw) as c:
            mid = (await _create_match(c, t, p1, p2)).json()['id']
            winner = await MatchPlayers.filter(match_id=mid).first()
            resp = await c.post(f'/api/matches/{mid}/result', json={'winner_id': winner.id})
            assert resp.status_code == 200
            ranks = {p['id']: p['finish_rank'] for p in resp.json()['players']}
            assert ranks[winner.id] == 1

    async def test_delete_match(self, db, app):
        _, raw = await create_user_token(username='boss', roles=[Role.STAFF])
        t, p1, p2 = await _tournament_and_players()
        async with client_for(app, raw) as c:
            mid = (await _create_match(c, t, p1, p2)).json()['id']
            assert (await c.delete(f'/api/matches/{mid}')).status_code == 204
            assert (await c.get(f'/api/matches/{mid}')).status_code == 404


class TestCrewAndAck:
    async def test_signup_approve_acknowledge(self, db, app):
        _, staff_raw = await create_user_token(username='boss', roles=[Role.STAFF])
        caster, caster_raw = await create_user_token(username='caster')
        t, p1, p2 = await _tournament_and_players()

        async with client_for(app, staff_raw) as staff, client_for(app, caster_raw) as caster_c:
            mid = (await _create_match(staff, t, p1, p2)).json()['id']

            # Caster signs themselves up as a commentator (pending).
            signup = await caster_c.post(f'/api/matches/{mid}/crew', json={'role': 'commentator'})
            assert signup.status_code == 201

            crew = await Commentator.filter(match_id=mid, user_id=caster.id).first()
            # A non-moderator caster cannot approve their own signup.
            self_approve = await caster_c.post(
                f'/api/crew/commentator/{crew.id}/approval', json={'approved': True}
            )
            assert self_approve.status_code == 403

            # Staff approves, then the caster acknowledges.
            assert (await staff.post(
                f'/api/crew/commentator/{crew.id}/approval', json={'approved': True}
            )).status_code == 200
            assert (await caster_c.post(
                f'/api/crew/commentator/{crew.id}/acknowledge'
            )).status_code == 200

    async def test_player_acknowledges_match(self, db, app):
        _, staff_raw = await create_user_token(username='boss', roles=[Role.STAFF])
        t, p1, p2 = await _tournament_and_players()
        _, p1_raw = await ApiToken_for(p1)

        async with client_for(app, staff_raw) as staff, client_for(app, p1_raw) as player:
            mid = (await _create_match(staff, t, p1, p2)).json()['id']
            resp = await player.post(f'/api/matches/{mid}/acknowledge')
            assert resp.status_code == 200


async def ApiToken_for(user: User):
    """Mint a token for an already-created user."""
    from application.services.api_token_service import ApiTokenService
    return await ApiTokenService().create_token(user, name='test')
