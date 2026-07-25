"""REST API tests for attaching a manually-scheduled match to a matchup.

Covers ``POST /brackets/matches/{id}/games/link`` and
``DELETE /brackets/games/by-match/{id}`` — the staff correction path that lets a
match created in the ordinary editor settle a bracket matchup. Split from
``test_brackets_management.py`` to keep both modules under the file-length
guideline.
"""

from application.services.api_token_service import ApiTokenService
from models import Role, Tournament
from tests.api_helpers import client_for, create_user_token
from tests.factories import make_user


async def _staff_token(username='staff'):
    return await create_user_token(username=username, roles=[Role.STAFF])


async def _tournament(name='Cup'):
    return await Tournament.create(name=name)


async def _token_for(user):
    """A write token for an already-created user (not a freshly-made one)."""
    _, raw = await ApiTokenService().create_token(user, name='test')
    return raw


async def _draft(c, tournament):
    return (await c.post('/api/brackets', json={
        'tournament_id': tournament.id, 'name': 'Main', 'format': 'single_elim',
    })).json()['id']


async def _enroll(c, bracket_id, tournament, names, *, user_ids=()):
    """Add each name as an entrant and enroll it; returns the entry ids in order."""
    entry_ids = []
    for i, name in enumerate(names):
        body = {'tournament_id': tournament.id, 'display_name': name}
        if user_ids:
            body['user_id'] = user_ids[i]
        entrant = (await c.post('/api/brackets/entrants', json=body)).json()
        entry_ids.append((await c.post(
            f'/api/brackets/{bracket_id}/entries', json={'entrant_id': entrant['id']},
        )).json()['id'])
    return entry_ids


class TestGameLinking:
    async def _started(self, c, tournament, users):
        bracket_id = await _draft(c, tournament)
        await _enroll(
            c, bracket_id, tournament, ('Alice', 'Bob'),
            user_ids=[u.id for u in users],
        )
        await c.post(f'/api/brackets/{bracket_id}/start')
        matches = (await c.get(f'/api/brackets/{bracket_id}/matches')).json()
        return matches[0]['id']

    async def test_links_an_existing_match(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        alice = await make_user(discord_id=9401, username='alice')
        bob = await make_user(discord_id=9402, username='bob')
        async with client_for(app, staff) as c:
            bmatch_id = await self._started(c, t, (alice, bob))
            match_id = (await c.post('/api/matches', json={
                'tournament_id': t.id,
                'scheduled_date': '2026-06-12',
                'scheduled_time': '14:30',
                'player_ids': [alice.id, bob.id],
            })).json()['id']

            r = await c.post(
                f'/api/brackets/matches/{bmatch_id}/games/link',
                json={'scheduled_match_id': match_id},
            )
            assert r.status_code == 201
            games = r.json()['games']
            assert [g['game_number'] for g in games] == [1]

    async def test_mismatched_players_rejected(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        alice = await make_user(discord_id=9411, username='alice')
        bob = await make_user(discord_id=9412, username='bob')
        stranger = await make_user(discord_id=9413, username='stranger')
        async with client_for(app, staff) as c:
            bmatch_id = await self._started(c, t, (alice, bob))
            match_id = (await c.post('/api/matches', json={
                'tournament_id': t.id,
                'scheduled_date': '2026-06-12',
                'scheduled_time': '14:30',
                'player_ids': [alice.id, stranger.id],
            })).json()['id']

            r = await c.post(
                f'/api/brackets/matches/{bmatch_id}/games/link',
                json={'scheduled_match_id': match_id},
            )
            assert r.status_code == 400

    async def test_unlink_frees_the_slot(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        alice = await make_user(discord_id=9421, username='alice')
        bob = await make_user(discord_id=9422, username='bob')
        async with client_for(app, staff) as c:
            bmatch_id = await self._started(c, t, (alice, bob))
            match_id = (await c.post('/api/matches', json={
                'tournament_id': t.id,
                'scheduled_date': '2026-06-12',
                'scheduled_time': '14:30',
                'player_ids': [alice.id, bob.id],
            })).json()['id']
            await c.post(
                f'/api/brackets/matches/{bmatch_id}/games/link',
                json={'scheduled_match_id': match_id},
            )

            assert (await c.delete(
                f'/api/brackets/games/by-match/{match_id}'
            )).status_code == 204
            r = await c.get(f'/api/brackets/matches/{bmatch_id}')
            assert r.json()['games'] == []

    async def test_unlinked_match_404s(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        alice = await make_user(discord_id=9431, username='alice')
        async with client_for(app, staff) as c:
            match_id = (await c.post('/api/matches', json={
                'tournament_id': t.id,
                'scheduled_date': '2026-06-12',
                'scheduled_time': '14:30',
                'player_ids': [alice.id],
            })).json()['id']
            assert (await c.delete(
                f'/api/brackets/games/by-match/{match_id}'
            )).status_code == 404

    async def test_entrant_cannot_link(self, db, app):
        """Players schedule from the bracket; linking is a staff correction."""
        _, staff = await _staff_token()
        t = await _tournament()
        alice = await make_user(discord_id=9441, username='alice')
        bob = await make_user(discord_id=9442, username='bob')
        async with client_for(app, staff) as c:
            bmatch_id = await self._started(c, t, (alice, bob))
            match_id = (await c.post('/api/matches', json={
                'tournament_id': t.id,
                'scheduled_date': '2026-06-12',
                'scheduled_time': '14:30',
                'player_ids': [alice.id, bob.id],
            })).json()['id']

        async with client_for(app, await _token_for(alice)) as c:
            r = await c.post(
                f'/api/brackets/matches/{bmatch_id}/games/link',
                json={'scheduled_match_id': match_id},
            )
            assert r.status_code == 403
