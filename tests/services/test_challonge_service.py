"""Unit tests for ChallongeService.

The HTTP client is replaced with a fake (the service builds clients via
``_api_client`` / ``_oauth_client``, which we override per-test). The bracket
mirror, participant→user resolution, scheduling, and result-push logic run
against a real in-memory DB so the mapping is exercised end to end.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.services.challonge_service import ChallongeService
from models import (
    ChallongeConnection,
    ChallongeMatch,
    ChallongeMatchState,
    ChallongeParticipant,
    Match,
    MatchPlayers,
    Tournament,
    User,
)


@pytest.fixture(autouse=True)
def bypass_auth(monkeypatch):
    from application.services import auth_service

    async def allow(*_args, **_kwargs):
        return True

    async def noop_ensure(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth_service.AuthService, 'is_staff', allow)
    monkeypatch.setattr(auth_service.AuthService, 'can_edit_tournament', allow)
    monkeypatch.setattr(auth_service.AuthService, 'ensure', noop_ensure)


def make_service(api=None, oauth=None) -> ChallongeService:
    service = ChallongeService()
    if api is not None:
        service._api_client = lambda: api
    if oauth is not None:
        service._oauth_client = lambda: oauth
    return service


async def make_user(discord_id: int, username: str = 'u', challonge_user_id=None) -> User:
    return await User.create(
        discord_id=discord_id, username=username, challonge_user_id=challonge_user_id,
    )


# ----------------------------------------------------------------------
# parse_tournament_identifier (pure)
# ----------------------------------------------------------------------
class TestParseIdentifier:
    def test_plain_slug(self):
        assert ChallongeService.parse_tournament_identifier('abc123') == 'abc123'

    def test_numeric_id(self):
        assert ChallongeService.parse_tournament_identifier('12345') == '12345'

    def test_root_url(self):
        assert ChallongeService.parse_tournament_identifier('https://challonge.com/abc123') == 'abc123'

    def test_subdomain_url(self):
        assert (
            ChallongeService.parse_tournament_identifier('https://myorg.challonge.com/spring25')
            == 'myorg-spring25'
        )

    def test_blank_raises(self):
        with pytest.raises(ValueError):
            ChallongeService.parse_tournament_identifier('   ')


# ----------------------------------------------------------------------
# get_valid_access_token
# ----------------------------------------------------------------------
class TestGetValidAccessToken:
    async def test_no_connection_raises(self, db):
        with pytest.raises(ValueError, match='not connected'):
            await make_service().get_valid_access_token()

    async def test_returns_live_token(self, db):
        await ChallongeConnection.create(
            access_token='live', refresh_token='r',
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        assert await make_service().get_valid_access_token() == 'live'

    async def test_refreshes_when_expiring(self, db):
        await ChallongeConnection.create(
            access_token='old', refresh_token='r1',
            token_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        oauth = MagicMock()
        oauth.refresh = AsyncMock(return_value={
            'access_token': 'new', 'refresh_token': 'r2', 'expires_in': 604800,
        })
        token = await make_service(oauth=oauth).get_valid_access_token()
        assert token == 'new'
        oauth.refresh.assert_awaited_once_with('r1')
        connection = await ChallongeConnection.all().first()
        assert connection.access_token == 'new'
        assert connection.refresh_token == 'r2'

    async def test_force_refresh_without_refresh_token_raises(self, db):
        await ChallongeConnection.create(access_token='only', refresh_token=None)
        with pytest.raises(ValueError, match='reconnect'):
            await make_service().get_valid_access_token(force_refresh=True)


# ----------------------------------------------------------------------
# sync_bracket
# ----------------------------------------------------------------------
class TestSyncBracket:
    async def test_mirrors_participants_and_matches(self, db):
        actor = await make_user(1, 'admin')
        linked = await make_user(2, 'alice', challonge_user_id='1001')
        tournament = await Tournament.create(name='T', challonge_tournament_id='T1')

        api = MagicMock()
        api.get_tournament_full = AsyncMock(return_value={
            'tournament': {'id': 'T1', 'name': 'T', 'url': None, 'state': 'underway'},
            'participants': [
                {'participant_id': '9001', 'name': 'Alice', 'challonge_user_id': '1001', 'username': 'alice'},
                {'participant_id': '9002', 'name': 'Bob', 'challonge_user_id': '9999', 'username': 'bob'},
            ],
            'matches': [
                {'match_id': '8001', 'state': 'open', 'round': 1,
                 'player1_participant_id': '9001', 'player2_participant_id': '9002',
                 'winner_participant_id': None},
            ],
        })

        result = await make_service(api=api).sync_bracket(tournament.id, actor)
        assert result == {'participants': 2, 'matches': 1}

        alice_p = await ChallongeParticipant.get(tournament=tournament, challonge_participant_id='9001')
        assert alice_p.user_id == linked.id  # resolved by challonge_user_id
        bob_p = await ChallongeParticipant.get(tournament=tournament, challonge_participant_id='9002')
        assert bob_p.user_id is None  # unlinked

        cmatch = await ChallongeMatch.get(tournament=tournament, challonge_match_id='8001')
        assert cmatch.state == ChallongeMatchState.OPEN
        assert cmatch.participant1_id == alice_p.id
        assert cmatch.participant2_id == bob_p.id

    async def test_requires_linked_tournament(self, db):
        actor = await make_user(1, 'admin')
        tournament = await Tournament.create(name='T')  # no challonge id
        with pytest.raises(ValueError, match='not linked'):
            await make_service().sync_bracket(tournament.id, actor)

    async def test_throttles_repeat_sync_without_force(self, db):
        actor = await make_user(1, 'admin')
        tournament = await Tournament.create(name='T', challonge_tournament_id='T1')

        api = MagicMock()
        api.get_tournament_full = AsyncMock(return_value={
            'tournament': {'id': 'T1', 'name': 'T', 'url': None, 'state': 'underway'},
            'participants': [], 'matches': [],
        })
        service = make_service(api=api)

        await service.sync_bracket(tournament.id, actor)
        # Second non-forced sync within the throttle window must not hit the API.
        result = await service.sync_bracket(tournament.id, actor)
        assert result.get('skipped') is True
        api.get_tournament_full.assert_awaited_once()

        # Forcing overrides the throttle.
        await service.sync_bracket(tournament.id, actor, force=True)
        assert api.get_tournament_full.await_count == 2


# ----------------------------------------------------------------------
# schedule_challonge_match
# ----------------------------------------------------------------------
class TestScheduleChallongeMatch:
    async def _open_match(self, tournament, p1_user, p2_user):
        p1 = await ChallongeParticipant.create(
            tournament=tournament, challonge_participant_id='9001', name='P1',
            challonge_user_id=p1_user.challonge_user_id, user=p1_user,
        )
        p2 = await ChallongeParticipant.create(
            tournament=tournament, challonge_participant_id='9002', name='P2',
            challonge_user_id=p2_user.challonge_user_id, user=p2_user,
        )
        return await ChallongeMatch.create(
            tournament=tournament, challonge_match_id='8001', round=1,
            state=ChallongeMatchState.OPEN, participant1=p1, participant2=p2,
        )

    async def test_happy_path_links_match(self, db, monkeypatch):
        actor = await make_user(1, 'alice', challonge_user_id='1001')
        opponent = await make_user(2, 'bob', challonge_user_id='1002')
        tournament = await Tournament.create(name='T', challonge_tournament_id='T1')
        cmatch = await self._open_match(tournament, actor, opponent)

        created_match = await Match.create(tournament=tournament)
        fake_ms = MagicMock()
        fake_ms.submit_match_request = AsyncMock(return_value=created_match)
        monkeypatch.setattr('application.services.challonge_service.MatchService', lambda: fake_ms)

        returned = await make_service().schedule_challonge_match(
            challonge_match_pk=cmatch.id, scheduled_date='2026-06-12', scheduled_time='14:30', actor=actor,
        )
        assert returned.id == created_match.id
        fake_ms.submit_match_request.assert_awaited_once()
        _, kwargs = fake_ms.submit_match_request.call_args
        assert sorted(kwargs['player_ids']) == sorted([actor.id, opponent.id])

        await cmatch.refresh_from_db()
        assert cmatch.match_id == created_match.id

    async def test_unlinked_opponent_raises(self, db):
        actor = await make_user(1, 'alice', challonge_user_id='1001')
        tournament = await Tournament.create(name='T', challonge_tournament_id='T1')
        # participant2 has no user
        p1 = await ChallongeParticipant.create(
            tournament=tournament, challonge_participant_id='9001', name='P1',
            challonge_user_id='1001', user=actor,
        )
        p2 = await ChallongeParticipant.create(
            tournament=tournament, challonge_participant_id='9002', name='P2', user=None,
        )
        cmatch = await ChallongeMatch.create(
            tournament=tournament, challonge_match_id='8001', state=ChallongeMatchState.OPEN,
            participant1=p1, participant2=p2,
        )
        with pytest.raises(ValueError, match='link their Challonge account'):
            await make_service().schedule_challonge_match(
                challonge_match_pk=cmatch.id, scheduled_date='2026-06-12', scheduled_time='14:30', actor=actor,
            )

    async def test_already_scheduled_raises(self, db):
        actor = await make_user(1, 'alice', challonge_user_id='1001')
        opponent = await make_user(2, 'bob', challonge_user_id='1002')
        tournament = await Tournament.create(name='T', challonge_tournament_id='T1')
        cmatch = await self._open_match(tournament, actor, opponent)
        existing = await Match.create(tournament=tournament)
        cmatch.match = existing
        await cmatch.save()
        with pytest.raises(ValueError, match='already been scheduled'):
            await make_service().schedule_challonge_match(
                challonge_match_pk=cmatch.id, scheduled_date='2026-06-12', scheduled_time='14:30', actor=actor,
            )


# ----------------------------------------------------------------------
# push_match_result
# ----------------------------------------------------------------------
class TestPushMatchResult:
    async def _setup(self, winner_rank_set=True):
        actor = await make_user(1, 'admin')
        winner = await make_user(2, 'alice', challonge_user_id='1001')
        loser = await make_user(3, 'bob', challonge_user_id='1002')
        tournament = await Tournament.create(name='T', challonge_tournament_id='T1')
        match = await Match.create(tournament=tournament)
        await MatchPlayers.create(match=match, user=winner, finish_rank=1 if winner_rank_set else None)
        await MatchPlayers.create(match=match, user=loser, finish_rank=2 if winner_rank_set else None)
        p1 = await ChallongeParticipant.create(
            tournament=tournament, challonge_participant_id='100', name='Alice',
            challonge_user_id='1001', user=winner,
        )
        p2 = await ChallongeParticipant.create(
            tournament=tournament, challonge_participant_id='200', name='Bob',
            challonge_user_id='1002', user=loser,
        )
        cmatch = await ChallongeMatch.create(
            tournament=tournament, challonge_match_id='8001', state=ChallongeMatchState.OPEN,
            participant1=p1, participant2=p2, match=match,
        )
        return actor, match, cmatch

    async def test_pushes_winner_and_loser(self, db):
        actor, match, _ = await self._setup()
        api = MagicMock()
        api.update_match = AsyncMock()
        # The push triggers a single post-push re-sync to mirror bracket advancement.
        api.get_tournament_full = AsyncMock(return_value={
            'tournament': {'id': 'T1', 'name': 'T', 'url': None, 'state': 'underway'},
            'participants': [], 'matches': [],
        })
        await make_service(api=api).push_match_result(match, actor)
        api.update_match.assert_awaited_once()
        _, kwargs = api.update_match.call_args
        assert kwargs['winner_participant_id'] == '100'
        assert kwargs['loser_participant_id'] == '200'
        assert kwargs['match_id'] == '8001'
        assert kwargs['tournament_id'] == 'T1'
        api.get_tournament_full.assert_awaited_once()

    async def test_no_winner_recorded_raises(self, db):
        actor, match, _ = await self._setup(winner_rank_set=False)
        with pytest.raises(ValueError, match='No winner'):
            await make_service().push_match_result(match, actor)

    async def test_unlinked_match_raises(self, db):
        actor = await make_user(1, 'admin')
        tournament = await Tournament.create(name='T')
        match = await Match.create(tournament=tournament)
        with pytest.raises(ValueError, match='not linked'):
            await make_service().push_match_result(match, actor)

    async def test_push_if_linked_skips_unlinked(self, db):
        actor = await make_user(1, 'admin')
        tournament = await Tournament.create(name='T')
        match = await Match.create(tournament=tournament)
        attempted = await make_service().push_result_if_linked(match, actor)
        assert attempted is False


# ----------------------------------------------------------------------
# Player identity linking
# ----------------------------------------------------------------------
class TestPlayerLink:
    async def test_record_and_unlink(self, db):
        user = await make_user(1, 'alice')
        service = make_service()
        await service.record_player_link(user, '1001', 'alice_c', actor=user)
        await user.refresh_from_db()
        assert user.challonge_user_id == '1001'
        assert user.challonge_username == 'alice_c'
        assert user.challonge_linked_at is not None

        await service.unlink_player(user, actor=user)
        await user.refresh_from_db()
        assert user.challonge_user_id is None
        assert user.challonge_username is None
        assert user.challonge_linked_at is None
