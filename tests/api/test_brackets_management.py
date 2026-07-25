"""REST API tests for the bracket management endpoints (api/routers/brackets.py).

Peer of ``test_api_brackets.py``, which covers the create → start → report →
complete happy path and the auth matrix. This module covers the management and
correction surface layered on top: editing a DRAFT bracket, round metadata,
reseeding, dropping an entrant, overriding a reported result, the single-match
read, a player's own open matchups, live standings and the advance dry run.
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


async def _draft(c, tournament, **kwargs):
    payload = {
        'tournament_id': tournament.id, 'name': 'Main', 'format': 'single_elim',
    }
    payload.update(kwargs)
    return (await c.post('/api/brackets', json=payload)).json()['id']


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


# --- editing the bracket definition ---------------------------------------


class TestBracketEditing:
    async def test_update_bracket(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)

            r = await c.patch(f'/api/brackets/{bracket_id}', json={'name': 'Playoffs'})
            assert r.status_code == 200
            assert r.json()['name'] == 'Playoffs'

            # An omitted field is left alone rather than nulled.
            r = await c.patch(f'/api/brackets/{bracket_id}', json={'stage_order': 3})
            assert r.status_code == 200
            assert r.json()['name'] == 'Playoffs'
            assert r.json()['stage_order'] == 3

    async def test_update_rejects_blank_name(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            r = await c.patch(f'/api/brackets/{bracket_id}', json={'name': '  '})
            assert r.status_code == 400

    async def test_update_rejects_started_bracket(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            await _enroll(c, bracket_id, t, ('Alice', 'Bob'))
            await c.post(f'/api/brackets/{bracket_id}/start')

            r = await c.patch(f'/api/brackets/{bracket_id}', json={'name': 'Nope'})
            assert r.status_code == 400

    async def test_update_rejects_taken_stage_order(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            await _draft(c, t, name='Groups', stage_order=0)
            second = await _draft(c, t, name='Playoffs', stage_order=1)
            r = await c.patch(f'/api/brackets/{second}', json={'stage_order': 0})
            assert r.status_code == 400

    async def test_delete_bracket(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            assert (await c.delete(f'/api/brackets/{bracket_id}')).status_code == 204
            assert (await c.get(f'/api/brackets/{bracket_id}')).status_code == 404

    async def test_delete_rejects_started_bracket(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            await _enroll(c, bracket_id, t, ('Alice', 'Bob'))
            await c.post(f'/api/brackets/{bracket_id}/start')
            assert (await c.delete(f'/api/brackets/{bracket_id}')).status_code == 400

    async def test_delete_read_only_forbidden(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
        _, ro = await create_user_token(username='ro', roles=[Role.STAFF], read_only=True)
        async with client_for(app, ro) as c:
            assert (await c.delete(f'/api/brackets/{bracket_id}')).status_code == 403

    async def test_delete_missing_bracket_404(self, db, app):
        _, staff = await _staff_token()
        async with client_for(app, staff) as c:
            assert (await c.delete('/api/brackets/999999')).status_code == 404


class TestRoundMetadata:
    async def test_round_metadata_round_trips_and_clears(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)

            r = await c.put(f'/api/brackets/{bracket_id}/rounds', json={
                'rounds': {'1': {'best_of': 3, 'scheduled_at': '2026-06-12T18:00:00'}},
            })
            assert r.status_code == 200
            assert r.json()['config']['rounds']['1']['best_of'] == 3

            cleared = await c.put(
                f'/api/brackets/{bracket_id}/rounds', json={'rounds': None},
            )
            assert cleared.status_code == 200
            assert 'rounds' not in (cleared.json()['config'] or {})

    async def test_round_metadata_editable_after_start(self, db, app):
        """Round chrome is display-only, so unlike PATCH it survives ACTIVE."""
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            await _enroll(c, bracket_id, t, ('Alice', 'Bob'))
            await c.post(f'/api/brackets/{bracket_id}/start')

            r = await c.put(f'/api/brackets/{bracket_id}/rounds', json={
                'rounds': {'1': {'best_of': 5}},
            })
            assert r.status_code == 200
            assert r.json()['config']['rounds']['1']['best_of'] == 5

    async def test_round_metadata_rejects_even_best_of(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            r = await c.put(f'/api/brackets/{bracket_id}/rounds', json={
                'rounds': {'1': {'best_of': 2}},
            })
            assert r.status_code == 400


class TestSeeds:
    async def test_set_seeds(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            first, second = await _enroll(c, bracket_id, t, ('Alice', 'Bob'))

            r = await c.patch(f'/api/brackets/{bracket_id}/seeds', json={
                'seeds': {str(first): 2, str(second): 1},
            })
            assert r.status_code == 200
            # Returned in the new seed order.
            assert [row['seed'] for row in r.json()] == [1, 2]
            assert [row['id'] for row in r.json()] == [second, first]

    async def test_set_seeds_rejects_duplicate_and_writes_nothing(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            first, second = await _enroll(c, bracket_id, t, ('Alice', 'Bob'))

            bad = await c.patch(f'/api/brackets/{bracket_id}/seeds', json={
                'seeds': {str(first): 1, str(second): 1},
            })
            assert bad.status_code == 400
            entries = (await c.get(f'/api/brackets/{bracket_id}/entries')).json()
            assert all(row['seed'] is None for row in entries)

    async def test_set_seeds_rejects_zero(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            first, _second = await _enroll(c, bracket_id, t, ('Alice', 'Bob'))
            r = await c.patch(f'/api/brackets/{bracket_id}/seeds', json={
                'seeds': {str(first): 0},
            })
            assert r.status_code == 400

    async def test_set_seeds_rejects_foreign_entry(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            a = await _draft(c, t, name='A', stage_order=0)
            b = await _draft(c, t, name='B', stage_order=1)
            (entry_in_a,) = await _enroll(c, a, t, ('Alice',))
            r = await c.patch(f'/api/brackets/{b}/seeds', json={
                'seeds': {str(entry_in_a): 1},
            })
            assert r.status_code == 400

    async def test_set_seeds_read_only_forbidden(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            (entry_id,) = await _enroll(c, bracket_id, t, ('Alice',))
        _, ro = await create_user_token(username='ro', roles=[Role.STAFF], read_only=True)
        async with client_for(app, ro) as c:
            r = await c.patch(f'/api/brackets/{bracket_id}/seeds', json={
                'seeds': {str(entry_id): 1},
            })
            assert r.status_code == 403


# --- roster ---------------------------------------------------------------


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

    async def test_drop_role_less_forbidden(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            entrant = await self._entrant(c, t)
        _, plain = await create_user_token(username='plain')
        async with client_for(app, plain) as c:
            r = await c.post(f"/api/brackets/entrants/{entrant['id']}/drop")
            assert r.status_code == 403


# --- reads ----------------------------------------------------------------


class TestMatchRead:
    async def test_get_match_with_games(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            await _enroll(c, bracket_id, t, ('Alice', 'Bob'))
            await c.post(f'/api/brackets/{bracket_id}/start')
            match_id = (await c.get(f'/api/brackets/{bracket_id}/matches')).json()[0]['id']

            r = await c.get(f'/api/brackets/matches/{match_id}')
            assert r.status_code == 200
            assert r.json()['id'] == match_id
            # Game rows are created lazily, so an unscheduled series has none.
            assert r.json()['games'] == []

    async def test_get_match_not_found(self, db, app):
        _, staff = await _staff_token()
        async with client_for(app, staff) as c:
            assert (await c.get('/api/brackets/matches/999999')).status_code == 404

    async def test_get_match_readable_with_role_less_token(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            await _enroll(c, bracket_id, t, ('Alice', 'Bob'))
            await c.post(f'/api/brackets/{bracket_id}/start')
            match_id = (await c.get(f'/api/brackets/{bracket_id}/matches')).json()[0]['id']
        _, plain = await create_user_token(username='plain')
        async with client_for(app, plain) as c:
            assert (await c.get(f'/api/brackets/matches/{match_id}')).status_code == 200


class TestMyOpenMatches:
    async def _linked_bracket(self, c, tournament, users):
        bracket_id = await _draft(c, tournament)
        await _enroll(
            c, bracket_id, tournament, ('Alice', 'Bob'),
            user_ids=[u.id for u in users],
        )
        await c.post(f'/api/brackets/{bracket_id}/start')
        return bracket_id

    async def test_lists_only_the_callers_matchups(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        alice = await make_user(discord_id=9301, username='alice')
        bob = await make_user(discord_id=9302, username='bob')
        async with client_for(app, staff) as c:
            await self._linked_bracket(c, t, (alice, bob))

        # A user who is not an entrant sees nothing.
        _, outsider = await create_user_token(username='outsider')
        async with client_for(app, outsider) as c:
            assert (await c.get('/api/brackets/my-open-matches')).json() == []

        async with client_for(app, await _token_for(alice)) as c:
            r = await c.get('/api/brackets/my-open-matches')
            assert r.status_code == 200
            assert len(r.json()) == 1

    async def test_tournament_filter(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        alice = await make_user(discord_id=9311, username='alice')
        bob = await make_user(discord_id=9312, username='bob')
        async with client_for(app, staff) as c:
            await self._linked_bracket(c, t, (alice, bob))

        async with client_for(app, await _token_for(alice)) as c:
            same = await c.get(f'/api/brackets/my-open-matches?tournament_id={t.id}')
            assert len(same.json()) == 1
            other = await c.get('/api/brackets/my-open-matches?tournament_id=999999')
            assert other.json() == []

    async def test_unlinked_entrants_are_excluded(self, db, app):
        """A matchup is only listed when *both* entrants resolve to a user."""
        _, staff = await _staff_token()
        t = await _tournament()
        alice = await make_user(discord_id=9321, username='alice')
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            entrant = (await c.post('/api/brackets/entrants', json={
                'tournament_id': t.id, 'display_name': 'Alice', 'user_id': alice.id,
            })).json()
            await c.post(f'/api/brackets/{bracket_id}/entries', json={
                'entrant_id': entrant['id'],
            })
            # Bob has no linked user.
            unlinked = (await c.post('/api/brackets/entrants', json={
                'tournament_id': t.id, 'display_name': 'Bob',
            })).json()
            await c.post(f'/api/brackets/{bracket_id}/entries', json={
                'entrant_id': unlinked['id'],
            })
            await c.post(f'/api/brackets/{bracket_id}/start')

        async with client_for(app, await _token_for(alice)) as c:
            assert (await c.get('/api/brackets/my-open-matches')).json() == []

    async def test_unauthenticated_is_rejected(self, db, app):
        async with client_for(app, None) as c:
            assert (await c.get('/api/brackets/my-open-matches')).status_code == 401


# --- corrections ----------------------------------------------------------


class TestOverrideResult:
    async def _played(self, c, tournament):
        """A single-elim Bo1 played out; returns (bracket_id, the played match)."""
        bracket_id = await _draft(c, tournament)
        await _enroll(c, bracket_id, tournament, ('Alice', 'Bob'))
        await c.post(f'/api/brackets/{bracket_id}/start')
        match = (await c.get(f'/api/brackets/{bracket_id}/open-matches')).json()[0]
        await c.post(f"/api/brackets/matches/{match['id']}/result", json={
            'winner_entry_id': match['entry1_id'],
        })
        return bracket_id, match

    async def test_override_swaps_winner_and_reranks(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id, match = await self._played(c, t)

            r = await c.patch(f"/api/brackets/matches/{match['id']}/result", json={
                'winner_entry_id': match['entry2_id'],
                'entry1_score': 1, 'entry2_score': 3,
            })
            assert r.status_code == 200
            assert r.json()['winner_id'] == match['entry2_id']
            assert r.json()['entry1_score'] == 1
            assert r.json()['entry2_score'] == 3

            # The stage auto-finalized on the original result, so its ranks are
            # recomputed from the correction rather than left stale.
            entries = (await c.get(f'/api/brackets/{bracket_id}/entries')).json()
            champion = next(e for e in entries if e['final_rank'] == 1)
            assert champion['id'] == match['entry2_id']

    async def test_override_rejects_incomplete_match(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            await _enroll(c, bracket_id, t, ('Alice', 'Bob'))
            await c.post(f'/api/brackets/{bracket_id}/start')
            match = (await c.get(f'/api/brackets/{bracket_id}/open-matches')).json()[0]

            r = await c.patch(f"/api/brackets/matches/{match['id']}/result", json={
                'winner_entry_id': match['entry1_id'],
            })
            assert r.status_code == 400

    async def test_override_rejects_lower_winner_score(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            _bracket_id, match = await self._played(c, t)
            r = await c.patch(f"/api/brackets/matches/{match['id']}/result", json={
                'winner_entry_id': match['entry2_id'],
                'entry1_score': 3, 'entry2_score': 0,
            })
            assert r.status_code == 400

            ff = await c.patch(f"/api/brackets/matches/{match['id']}/result", json={
                'winner_entry_id': match['entry2_id'],
                'entry1_score': 3, 'entry2_score': 0, 'forfeit': True,
            })
            assert ff.status_code == 200
            assert ff.json()['forfeit'] is True

    async def test_override_missing_match_404(self, db, app):
        _, staff = await _staff_token()
        async with client_for(app, staff) as c:
            r = await c.patch('/api/brackets/matches/999999/result', json={
                'winner_entry_id': 1,
            })
            assert r.status_code == 404

    async def test_override_read_only_forbidden(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            _bracket_id, match = await self._played(c, t)
        _, ro = await create_user_token(username='ro', roles=[Role.STAFF], read_only=True)
        async with client_for(app, ro) as c:
            r = await c.patch(f"/api/brackets/matches/{match['id']}/result", json={
                'winner_entry_id': match['entry2_id'],
            })
            assert r.status_code == 403


# --- standings ------------------------------------------------------------


class TestStandings:
    async def _round_robin(self, c, tournament, names, *, group_count=1):
        bracket_id = await _draft(
            c, tournament, name='Groups', format='round_robin',
            config={'group_count': group_count},
        )
        await _enroll(c, bracket_id, tournament, names)
        await c.post(f'/api/brackets/{bracket_id}/start')
        return bracket_id

    async def _play_all(self, c, bracket_id, *, always_win=None):
        """Report every match, letting ``always_win`` (an entry id) win its games."""
        for m in (await c.get(f'/api/brackets/{bracket_id}/matches')).json():
            slots = (m['entry1_id'], m['entry2_id'])
            pick = always_win if always_win in slots else m['entry1_id']
            await c.post(f"/api/brackets/matches/{m['id']}/result", json={
                'winner_entry_id': pick,
            })

    async def test_standings_before_any_result(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await self._round_robin(
                c, t, ('Alice', 'Bob', 'Carol', 'Dave'),
            )
            groups = (await c.get(f'/api/brackets/{bracket_id}/standings')).json()
            assert len(groups) == 1
            rows = groups[0]['rows']
            assert len(rows) == 4
            assert {row['points'] for row in rows} == {0.0}
            assert {row['rank'] for row in rows} == {1}
            assert {row['display_name'] for row in rows} == {
                'Alice', 'Bob', 'Carol', 'Dave',
            }
            assert all(row['status'] == 'active' for row in rows)
            assert all(row['entrant_status'] == 'active' for row in rows)

    async def test_standings_rank_the_winner_first(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await self._round_robin(
                c, t, ('Alice', 'Bob', 'Carol', 'Dave'),
            )
            matches = (await c.get(f'/api/brackets/{bracket_id}/matches')).json()
            winner = matches[0]['entry1_id']
            await self._play_all(c, bracket_id, always_win=winner)

            rows = (await c.get(f'/api/brackets/{bracket_id}/standings')).json()[0]['rows']
            top = rows[0]
            assert top['entry_id'] == winner
            assert top['rank'] == 1
            assert top['wins'] == 3
            assert top['losses'] == 0
            assert top['points'] == 3.0
            assert 'buchholz' in top['tiebreakers']
            # Rows come back in rank order.
            assert [row['rank'] for row in rows] == sorted(row['rank'] for row in rows)
            # final_rank is only persisted once the stage completes.
            assert all(row['final_rank'] is None for row in rows)

            assert (await c.post(f'/api/brackets/{bracket_id}/complete')).status_code == 200
            rows = (await c.get(f'/api/brackets/{bracket_id}/standings')).json()[0]['rows']
            assert rows[0]['final_rank'] == 1

    async def test_standings_per_group(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await self._round_robin(
                c, t, ('Alice', 'Bob', 'Carol', 'Dave'), group_count=2,
            )
            groups = (await c.get(f'/api/brackets/{bracket_id}/standings')).json()
            assert len(groups) == 2
            assert all(len(g['rows']) == 2 for g in groups)
            # Groups come back in ascending group_number, and no entry is doubled up.
            numbers = [g['group_number'] for g in groups]
            assert numbers == sorted(numbers)
            entry_ids = [row['entry_id'] for g in groups for row in g['rows']]
            assert len(set(entry_ids)) == 4

    async def test_dropped_entrant_stays_in_the_table(self, db, app):
        """A roster drop keeps the row (its results still count) and is visible.

        The two drop levels are independent: `drop_entrant` writes the roster
        state only, so the row's stage-entry `status` stays ACTIVE while
        `entrant_status` flips to DROPPED.
        """
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await self._round_robin(c, t, ('Alice', 'Bob', 'Carol', 'Dave'))
            entries = (await c.get(f'/api/brackets/{bracket_id}/entries')).json()
            dropped_entry = entries[0]
            await c.post(f"/api/brackets/entrants/{dropped_entry['entrant_id']}/drop")

            rows = (await c.get(f'/api/brackets/{bracket_id}/standings')).json()[0]['rows']
            assert len(rows) == 4
            row = next(r for r in rows if r['entry_id'] == dropped_entry['id'])
            assert row['entrant_status'] == 'dropped'
            assert row['status'] == 'active'
            assert all(
                r['entrant_status'] == 'active'
                for r in rows if r['entry_id'] != dropped_entry['id']
            )

    async def test_swiss_standings_single_group(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t, name='Swiss', format='swiss')
            await _enroll(c, bracket_id, t, ('Alice', 'Bob', 'Carol', 'Dave'))
            await c.post(f'/api/brackets/{bracket_id}/start')

            groups = (await c.get(f'/api/brackets/{bracket_id}/standings')).json()
            assert len(groups) == 1
            assert groups[0]['group_number'] is None
            assert len(groups[0]['rows']) == 4

    async def test_elimination_standings_rejected(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await _draft(c, t)
            r = await c.get(f'/api/brackets/{bracket_id}/standings')
            assert r.status_code == 400
            assert 'round-robin' in r.json()['detail']

    async def test_standings_missing_bracket_404(self, db, app):
        _, staff = await _staff_token()
        async with client_for(app, staff) as c:
            assert (await c.get('/api/brackets/999999/standings')).status_code == 404

    async def test_standings_readable_with_role_less_token(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            bracket_id = await self._round_robin(c, t, ('Alice', 'Bob'))
        _, plain = await create_user_token(username='plain')
        async with client_for(app, plain) as c:
            r = await c.get(f'/api/brackets/{bracket_id}/standings')
            assert r.status_code == 200


# --- stage advancement dry run --------------------------------------------


class TestAdvancingPreview:
    async def test_preview_matches_the_advance(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            groups_id = await _draft(
                c, t, name='Groups', format='round_robin', stage_order=0,
                config={'group_count': 1},
            )
            await _draft(
                c, t, name='Playoffs', format='single_elim', stage_order=1,
                config={'advancement': {'count': 2}},
            )
            await _enroll(c, groups_id, t, ('Alice', 'Bob', 'Carol', 'Dave'))
            await c.post(f'/api/brackets/{groups_id}/start')

            # The source stage must complete before it can be previewed.
            early = await c.get(
                f'/api/brackets/advancing-preview'
                f'?tournament_id={t.id}&from_stage_order=0'
            )
            assert early.status_code == 400

            for m in (await c.get(f'/api/brackets/{groups_id}/matches')).json():
                await c.post(f"/api/brackets/matches/{m['id']}/result", json={
                    'winner_entry_id': m['entry1_id'],
                })
            await c.post(f'/api/brackets/{groups_id}/complete')

            preview = await c.get(
                f'/api/brackets/advancing-preview'
                f'?tournament_id={t.id}&from_stage_order=0'
            )
            assert preview.status_code == 200
            assert [row['final_rank'] for row in preview.json()] == [1, 2]
            previewed = [row['entrant_id'] for row in preview.json()]

            # The preview wrote nothing, and the real advance carries the same
            # field forward.
            advanced = await c.post(
                f'/api/brackets/advance-stage?tournament_id={t.id}',
                json={'from_stage_order': 0},
            )
            assert advanced.status_code == 200
            next_entries = (await c.get(
                f"/api/brackets/{advanced.json()['id']}/entries"
            )).json()
            assert sorted(row['entrant_id'] for row in next_entries) == sorted(previewed)

    async def test_preview_missing_stage_404(self, db, app):
        _, staff = await _staff_token()
        t = await _tournament()
        async with client_for(app, staff) as c:
            r = await c.get(
                f'/api/brackets/advancing-preview'
                f'?tournament_id={t.id}&from_stage_order=7'
            )
            assert r.status_code == 404

    async def test_preview_readable_with_role_less_token(self, db, app):
        """The dry run writes nothing, so it stays on the any-token read dep."""
        _, plain = await create_user_token(username='plain')
        t = await _tournament()
        async with client_for(app, plain) as c:
            r = await c.get(
                f'/api/brackets/advancing-preview'
                f'?tournament_id={t.id}&from_stage_order=0'
            )
            assert r.status_code == 404
