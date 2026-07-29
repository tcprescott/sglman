"""REST API tests for the bracket roster surface (entrants).

Peer of ``test_brackets_management.py``, which covers the stage definition,
seeding, corrections and reads. This module covers the tournament-level roster:
dropping an entrant, linking one to a user account, and importing the
tournament's enrolled players as entrants in one call.
"""

from models import Role, Tournament, TournamentPlayers
from tests.api_helpers import client_for, create_user_token
from tests.factories import make_user


async def _staff_token(username='staff'):
    return await create_user_token(username=username, roles=[Role.STAFF])


async def _tournament(name='Cup'):
    return await Tournament.create(name=name)


class TestEntrantDrop:
    async def _entrant(self, c, tournament, name='Alice'):
        return (await c.post('/api/brackets/entrants', json={
            'tournament_id': tournament.id, 'display_name': name,
        })).json()

    async def test_drop_entrant(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            entrant = await self._entrant(c, t)
            assert entrant['status'] == 'active'

            r = await c.post(f"/api/brackets/entrants/{entrant['id']}/drop")
            assert r.status_code == 200
            assert r.json()['status'] == 'dropped'

            listed = (await c.get(f'/api/brackets/entrants?tournament_id={t.id}')).json()
            assert [e['status'] for e in listed] == ['dropped']

    async def test_drop_missing_entrant_404(self, db, app):
        _, staff = await _staff_token()
        async with client_for(app, staff) as c:
            assert (await c.post('/api/brackets/entrants/999999/drop')).status_code == 404

    async def test_add_entrant_unknown_user_404s(self, db, app):
        """Not a 500: the unresolved FK used to escape as an IntegrityError,
        which both broke the error contract and oracled which user ids exist."""
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            r = await c.post('/api/brackets/entrants', json={
                'tournament_id': t.id, 'display_name': 'Ghost', 'user_id': 999999,
            })
            assert r.status_code == 404

    async def test_link_and_unlink_entrant_user(self, db, app):
        """The link is settable after creation — a placeholder can be resolved."""
        _, staff = await _staff_token()
        t = await _tournament()
        player = await make_user(discord_id=71, username='linkme')
        async with client_for(app, staff) as c:
            entrant = await self._entrant(c, t, name='Placeholder')
            assert entrant['user_id'] is None

            r = await c.patch(
                f"/api/brackets/entrants/{entrant['id']}/user",
                json={'user_id': player.id},
            )
            assert r.status_code == 200
            assert r.json()['user_id'] == player.id

            r = await c.patch(
                f"/api/brackets/entrants/{entrant['id']}/user", json={'user_id': None},
            )
            assert r.status_code == 200
            assert r.json()['user_id'] is None

    async def test_link_unknown_user_404s(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            entrant = await self._entrant(c, t)
            r = await c.patch(
                f"/api/brackets/entrants/{entrant['id']}/user", json={'user_id': 999999},
            )
            assert r.status_code == 404

    async def test_link_role_less_forbidden(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            entrant = await self._entrant(c, t)
        _, plain = await create_user_token(username='plain-link')
        async with client_for(app, plain) as c:
            r = await c.patch(
                f"/api/brackets/entrants/{entrant['id']}/user", json={'user_id': None},
            )
            assert r.status_code == 403

    async def test_drop_role_less_forbidden(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            entrant = await self._entrant(c, t)
        _, plain = await create_user_token(username='plain')
        async with client_for(app, plain) as c:
            r = await c.post(f"/api/brackets/entrants/{entrant['id']}/drop")
            assert r.status_code == 403


class TestRosterImport:
    async def _enrol_players(self, tournament, count):
        users = [
            await make_user(discord_id=800 + i, username=f'player{i}', display_name=f'Player {i}')
            for i in range(count)
        ]
        for u in users:
            await TournamentPlayers.create(
                tournament=tournament, user=u, tenant_id=tournament.tenant_id,
            )
        return users

    async def test_import_creates_a_linked_entrant_per_enrolled_player(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        users = await self._enrol_players(t, 3)
        async with client_for(app, staff) as c:
            r = await c.post('/api/brackets/entrants/import', json={'tournament_id': t.id})
            assert r.status_code == 201
            created = r.json()
            assert sorted(e['user_id'] for e in created) == sorted(u.id for u in users)
            assert sorted(e['display_name'] for e in created) == [
                'Player 0', 'Player 1', 'Player 2',
            ]

    async def test_import_is_idempotent(self, db, app):
        """Re-running after late signups adds only the new players."""
        _, staff = await _staff_token()
        t = await _tournament()
        await self._enrol_players(t, 2)
        async with client_for(app, staff) as c:
            assert len((await c.post(
                '/api/brackets/entrants/import', json={'tournament_id': t.id},
            )).json()) == 2

            assert (await c.post(
                '/api/brackets/entrants/import', json={'tournament_id': t.id},
            )).json() == []

            latecomer = await make_user(discord_id=900, username='late')
            await TournamentPlayers.create(
                tournament=t, user=latecomer, tenant_id=t.tenant_id,
            )
            second = (await c.post(
                '/api/brackets/entrants/import', json={'tournament_id': t.id},
            )).json()
            assert [e['user_id'] for e in second] == [latecomer.id]

            listed = (await c.get(f'/api/brackets/entrants?tournament_id={t.id}')).json()
            assert len(listed) == 3

    async def test_import_missing_tournament_404s(self, db, app):
        _, staff = await _staff_token()
        async with client_for(app, staff) as c:
            r = await c.post('/api/brackets/entrants/import', json={'tournament_id': 999999})
            assert r.status_code == 404

    async def test_import_role_less_forbidden(self, db, app):
        t = await _tournament()
        _, plain = await create_user_token(username='plain-import')
        async with client_for(app, plain) as c:
            r = await c.post('/api/brackets/entrants/import', json={'tournament_id': t.id})
            assert r.status_code == 403
