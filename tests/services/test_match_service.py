import itertools
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.match.match_service import MatchService
from tests.factories import make_audit_double, make_user

pytestmark = pytest.mark.usefixtures("bypass_auth")


@pytest.fixture(autouse=True)
def _no_tournament_window(monkeypatch):
    """Match tests don't set up tournament hours; suppress the scheduling window."""
    from application.services import system_config_service
    from application.services.match import match_service

    async def no_window(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        system_config_service.SystemConfigService,
        'get_tournament_window_for_date', no_window,
    )
    # The scheduling check loads the tournament (for its per-tournament hours
    # override) before consulting the window; these no-DB unit tests stub it out.
    monkeypatch.setattr(
        match_service.Tournament, 'get_or_none', AsyncMock(return_value=None),
    )


@pytest.fixture
def service():
    svc = object.__new__(MatchService)
    svc.repository = MagicMock()
    svc.repository.get_players = AsyncMock(return_value=[])
    svc.repository.occupied_stations = AsyncMock(return_value={})
    svc.station_repository = MagicMock()
    svc.station_repository.active_names = AsyncMock(return_value=set())
    svc.stage_repository = MagicMock()
    svc.tournament_repository = MagicMock()
    # create_match resolves the tournament through the scoped repository before
    # anything else, so the default has to be "it exists in this community".
    svc.tournament_repository.get_by_id = AsyncMock(
        return_value=SimpleNamespace(id=1, name="Test Tournament")
    )
    svc.user_repository = MagicMock()
    svc.commentator_repository = MagicMock()
    svc.tracker_repository = MagicMock()
    svc.ack_repository = MagicMock()
    svc.ack_repository.delete_for_match = AsyncMock()
    svc.ack_repository.upsert = AsyncMock()
    svc.ack_repository.list_for_match = AsyncMock(return_value=[])
    svc.ack_repository.list_for_matches = AsyncMock(return_value={})
    svc.ack_repository.get = AsyncMock(return_value=None)
    svc.audit_service = make_audit_double()
    svc.match_schedule_service = MagicMock()
    svc.match_schedule_service.notify_acknowledgment_request = AsyncMock()
    svc.match_schedule_service.notify_match_crew = AsyncMock()
    return svc


def make_match(**overrides):
    defaults = dict(
        id=1,
        tournament_id=1,
        seated_at=None,
        started_at=None,
        finished_at=None,
        confirmed_at=None,
        created_at=datetime(2025, 1, 1, 12, 0),
        scheduled_at=datetime(2025, 1, 15, 19, 30),
        comment=None,
        tournament=SimpleNamespace(name="Test Tournament", seed_generator=None, is_racetime_enabled=False),
        stage=None,
        stage_id=None,
        generated_seed=None,
        is_stream_candidate=False,
        players=[],
        commentators=[],
        trackers=[],
        fetch_related=AsyncMock(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def captured_events():
    """Subscribe to the event bus for the test and collect published events."""
    from application.events import event_bus

    seen = []
    token = event_bus.subscribe_sync(seen.append)
    yield seen
    event_bus.unsubscribe(token)


# ---------------------------------------------------------------------------
# create_match validation (no DB needed; error paths exit before any DB call)
# ---------------------------------------------------------------------------


class TestCreateMatchValidation:
    async def test_raises_when_player_ids_empty(self, service):
        with pytest.raises(ValueError, match="at least one player"):
            await service.create_match(
                tournament_id=1,
                scheduled_date="2025-01-15",
                scheduled_time="14:30",
                player_ids=[],
            )

    async def test_raises_on_invalid_date_format(self, service):
        with pytest.raises(ValueError):
            await service.create_match(
                tournament_id=1,
                scheduled_date="not-a-date",
                scheduled_time="14:30",
                player_ids=[1],
            )

    async def test_raises_on_invalid_time_format(self, service):
        with pytest.raises(ValueError):
            await service.create_match(
                tournament_id=1,
                scheduled_date="2025-01-15",
                scheduled_time="99:99",
                player_ids=[1],
            )


# Lifecycle transitions (seat/start/finish/confirm) are owned by
# MatchScheduleService._transition; see tests/services/test_match_schedule_service.py.
# The permissive MatchService.seat_players/finish_match duplicates were removed.


# ---------------------------------------------------------------------------
# create_match — subscriber notification fan-out
# ---------------------------------------------------------------------------


def _setup_create_match_mocks(service):
    """Wire up minimal mocks to let create_match reach its notification phase."""
    user = SimpleNamespace(id=1, discord_id=111)
    match = make_match(id=1, tournament_id=1, is_stream_candidate=False)

    service.repository.create = AsyncMock(return_value=match)
    service.user_repository.get_by_ids = AsyncMock(return_value={user.id: user})
    service.tournament_repository.get_enrolled_user_ids = AsyncMock(return_value={user.id})
    service.tournament_repository.enroll_player_by_id = AsyncMock()
    service.repository.add_player = AsyncMock()

    # create_match delegates the whole scheduled-notification fan-out to
    # MatchScheduleService.notify_match_scheduled (its internals — ack request,
    # crew, subscribers, stream-candidate — are covered in
    # test_match_schedule_service.py).
    service.match_schedule_service.notify_match_scheduled = AsyncMock()

    return match, user


class TestCreateMatchSubscriberNotifications:
    async def test_notify_match_scheduled_called(self, service):
        _setup_create_match_mocks(service)
        await service.create_match(
            tournament_id=1,
            scheduled_date="2025-01-15",
            scheduled_time="14:30",
            player_ids=[1],
        )
        service.match_schedule_service.notify_match_scheduled.assert_awaited_once()

    async def test_stream_candidate_flag_false_by_default(self, service):
        _setup_create_match_mocks(service)
        await service.create_match(
            tournament_id=1,
            scheduled_date="2025-01-15",
            scheduled_time="14:30",
            player_ids=[1],
            is_stream_candidate=False,
        )
        _, kwargs = service.match_schedule_service.notify_match_scheduled.call_args
        assert kwargs["is_stream_candidate"] is False

    async def test_stream_candidate_flag_passed_through_when_true(self, service):
        match, _ = _setup_create_match_mocks(service)
        match.is_stream_candidate = True
        service.repository.create = AsyncMock(return_value=match)
        await service.create_match(
            tournament_id=1,
            scheduled_date="2025-01-15",
            scheduled_time="14:30",
            player_ids=[1],
            is_stream_candidate=True,
        )
        _, kwargs = service.match_schedule_service.notify_match_scheduled.call_args
        assert kwargs["is_stream_candidate"] is True


# ---------------------------------------------------------------------------
# Acknowledgment seeding / acknowledge_match
# ---------------------------------------------------------------------------


class TestSeedAcknowledgments:
    async def test_actor_auto_acked_when_in_player_list(self, service):
        actor = SimpleNamespace(id=42)
        user = SimpleNamespace(id=42)
        service.user_repository.get_by_ids = AsyncMock(return_value={42: user})
        match = make_match()
        await service._seed_acknowledgments(match, [42], actor)
        service.ack_repository.delete_for_match.assert_awaited_once_with(match)
        call = service.ack_repository.upsert.await_args
        assert call.kwargs["acknowledged"] is True
        assert call.kwargs["auto"] is True

    async def test_non_actor_left_pending(self, service):
        actor = SimpleNamespace(id=42)
        opponent = SimpleNamespace(id=99)
        service.user_repository.get_by_ids = AsyncMock(return_value={99: opponent})
        match = make_match()
        await service._seed_acknowledgments(match, [99], actor)
        call = service.ack_repository.upsert.await_args
        assert call.kwargs["acknowledged"] is False
        assert call.kwargs["auto"] is False

    async def test_no_actor_means_no_auto_ack(self, service):
        user = SimpleNamespace(id=99)
        service.user_repository.get_by_ids = AsyncMock(return_value={99: user})
        match = make_match()
        await service._seed_acknowledgments(match, [99], None)
        call = service.ack_repository.upsert.await_args
        assert call.kwargs["acknowledged"] is False
        assert call.kwargs["auto"] is False


class TestAcknowledgeMatch:
    async def test_raises_when_match_not_found(self, service):
        service.repository.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="not found"):
            await service.acknowledge_match(match_id=1, user=SimpleNamespace(id=1))

    async def test_raises_when_user_not_a_player(self, service):
        match = make_match()
        service.repository.get_by_id = AsyncMock(return_value=match)
        service.repository.get_players = AsyncMock(return_value=[SimpleNamespace(user_id=999)])
        with pytest.raises(ValueError, match="not a participant"):
            await service.acknowledge_match(match_id=1, user=SimpleNamespace(id=1))

    async def test_raises_when_already_acknowledged(self, service):
        user = SimpleNamespace(id=42)
        match = make_match()
        service.repository.get_by_id = AsyncMock(return_value=match)
        service.repository.get_players = AsyncMock(return_value=[SimpleNamespace(user_id=42)])
        service.ack_repository.get = AsyncMock(
            return_value=SimpleNamespace(acknowledged_at=datetime(2026, 1, 1))
        )
        with pytest.raises(ValueError, match="already acknowledged"):
            await service.acknowledge_match(match_id=1, user=user)

    async def test_upserts_acknowledgment_when_pending(self, service):
        user = SimpleNamespace(id=42)
        match = make_match()
        service.repository.get_by_id = AsyncMock(return_value=match)
        service.repository.get_players = AsyncMock(return_value=[SimpleNamespace(user_id=42)])
        service.ack_repository.get = AsyncMock(return_value=None)
        await service.acknowledge_match(match_id=1, user=user)
        call = service.ack_repository.upsert.await_args
        assert call.kwargs["acknowledged"] is True
        assert call.kwargs["auto"] is False
        service.audit_service.write_log.assert_awaited_once()


# ---------------------------------------------------------------------------
# player / crew mutual exclusion
# ---------------------------------------------------------------------------


class TestPlayerCrewMutualExclusion:
    async def test_create_match_raises_when_player_is_commentator(self, service):
        user = SimpleNamespace(id=1, preferred_name="Alice")
        service.user_repository.get_by_ids = AsyncMock(return_value={1: user})
        with pytest.raises(ValueError, match="commentator"):
            await service.create_match(
                tournament_id=1,
                scheduled_date="2025-01-15",
                scheduled_time="14:30",
                player_ids=[1],
                commentator_ids=[1],
            )

    async def test_create_match_raises_when_player_is_tracker(self, service):
        user = SimpleNamespace(id=1, preferred_name="Alice")
        service.user_repository.get_by_ids = AsyncMock(return_value={1: user})
        with pytest.raises(ValueError, match="tracker"):
            await service.create_match(
                tournament_id=1,
                scheduled_date="2025-01-15",
                scheduled_time="14:30",
                player_ids=[1],
                tracker_ids=[1],
            )

    async def test_update_match_raises_when_player_assigned_as_commentator(self, service):
        match = make_match(commentators=[], trackers=[])
        service.repository.get_by_id = AsyncMock(return_value=match)
        service.repository.get_players = AsyncMock(return_value=[SimpleNamespace(user_id=7)])
        with pytest.raises(ValueError, match="commentator"):
            await service.update_match(match_id=1, player_ids=[7], commentator_ids=[7])

    async def test_update_match_raises_when_existing_player_added_as_tracker(self, service):
        match = make_match(commentators=[], trackers=[])
        service.repository.get_by_id = AsyncMock(return_value=match)
        service.repository.get_players = AsyncMock(return_value=[SimpleNamespace(user_id=7)])
        with pytest.raises(ValueError, match="tracker"):
            await service.update_match(match_id=1, tracker_ids=[7])


# ---------------------------------------------------------------------------
# assign_stage event publishing
# ---------------------------------------------------------------------------


class TestAssignStage:
    async def test_publishes_stage_assigned_event(
        self, service, captured_events, mocker,
    ):
        from application.events import EventType

        match = make_match(tournament_id=9)
        service.repository.get_by_id = AsyncMock(return_value=match)
        service.repository.update = AsyncMock()
        # The tenant guard hits the DB; this suite is pure-mock.
        mocker.patch(
            'application.services.match.match_service.StageService'
            '.require_in_tenant',
            AsyncMock(),
        )

        await service.assign_stage(match_id=1, stage_id=4)

        assert [e.event_type for e in captured_events] == [EventType.MATCH_STAGE_ASSIGNED]
        assert captured_events[0].payload == {
            'match_id': 1, 'tournament_id': 9, 'stage_id': 4,
        }

    async def test_publishes_stage_cleared_event_when_unassigned(self, service, captured_events):
        from application.events import EventType

        match = make_match(tournament_id=9)
        service.repository.get_by_id = AsyncMock(return_value=match)
        service.repository.update = AsyncMock()

        await service.assign_stage(match_id=1, stage_id=None)

        assert [e.event_type for e in captured_events] == [EventType.MATCH_STAGE_CLEARED]
        assert captured_events[0].payload['stage_id'] is None


# ---------------------------------------------------------------------------
# match lifecycle event publishing (delete / result / acknowledge / stations)
# ---------------------------------------------------------------------------


class TestMatchLifecycleEvents:
    async def test_delete_match_publishes_deleted_event(self, service, captured_events):
        from application.events import EventType

        match = make_match(id=1, tournament_id=9)
        service.repository.get_by_id = AsyncMock(return_value=match)
        service.repository.delete = AsyncMock()

        await service.delete_match(match_id=1, actor=SimpleNamespace(id=1))

        assert [e.event_type for e in captured_events] == [EventType.MATCH_DELETED]
        assert captured_events[0].payload == {'match_id': 1, 'tournament_id': 9}

    async def test_record_result_publishes_result_recorded_event(self, service, captured_events):
        from application.events import EventType

        p1 = SimpleNamespace(id=10, finish_rank=None, save=AsyncMock())
        p2 = SimpleNamespace(id=11, finish_rank=None, save=AsyncMock())
        match = make_match(tournament_id=9, players=[p1, p2])
        service.repository.get_by_id = AsyncMock(return_value=match)

        # This match backs no bracket game, which is the settled-result guard's
        # no-op path; stubbed because these lifecycle tests run without a DB.
        with patch(
            'application.services.bracket_service.BracketService.get_game_for_match',
            AsyncMock(return_value=None),
        ):
            await service.record_match_result(
                match_id=1, winner_id=10, actor=SimpleNamespace(id=1),
            )

        assert [e.event_type for e in captured_events] == [EventType.MATCH_RESULT_RECORDED]
        assert captured_events[0].payload == {
            'match_id': 1, 'tournament_id': 9, 'winner_id': 10,
            'ranks': {'10': 1, '11': 2},
        }

    async def test_acknowledge_match_publishes_acknowledged_event(self, service, captured_events):
        from application.events import EventType

        user = SimpleNamespace(id=42)
        match = make_match(tournament_id=9)
        service.repository.get_by_id = AsyncMock(return_value=match)
        service.repository.get_players = AsyncMock(return_value=[SimpleNamespace(user_id=42)])
        service.ack_repository.get = AsyncMock(return_value=None)

        await service.acknowledge_match(match_id=1, user=user)

        assert [e.event_type for e in captured_events] == [EventType.MATCH_ACKNOWLEDGED]
        assert captured_events[0].payload == {
            'match_id': 1, 'tournament_id': 9, 'user_id': 42,
        }

    async def test_assign_stations_publishes_stations_assigned_event(
        self, service, captured_events, monkeypatch
    ):
        from application.events import EventType
        from application.services import system_config_service
        from models import StationFormat

        async def free_format(*_args, **_kwargs):
            return StationFormat.FREE

        monkeypatch.setattr(
            system_config_service.SystemConfigService, 'get_station_format', free_format
        )

        player = SimpleNamespace(id=10, assigned_station=None, save=AsyncMock())
        match = make_match(tournament_id=9, players=[player])
        service.repository.get_by_id = AsyncMock(return_value=match)

        await service.assign_stations(
            match_id=1, assignments={10: 'A1'}, actor=SimpleNamespace(id=1)
        )

        assert [e.event_type for e in captured_events] == [EventType.MATCH_STATIONS_ASSIGNED]
        assert captured_events[0].payload == {
            'match_id': 1, 'tournament_id': 9, 'assignments': {'10': 'A1'},
        }


# ---------------------------------------------------------------------------
# station pool validation (T2.3) — real DB, since the ladder reads the station
# pool and derives occupancy from other matches.


_station_seq = itertools.count(1)


async def _make_onsite_match(*, seated=False, finished=False, stations=()):
    """A two-player on-site match, optionally seated/finished with stations set."""
    from models import Match, MatchPlayers, Tournament

    n = next(_station_seq)
    tournament = await Tournament.create(name=f'Station Cup {n}')
    match = await Match.create(
        tournament=tournament,
        seated_at=datetime(2025, 1, 15, 19, 0) if (seated or finished) else None,
        finished_at=datetime(2025, 1, 15, 20, 0) if finished else None,
    )
    players = []
    for slot in (1, 2):
        user = await make_user(discord_id=n * 10 + slot, username=f'station-{n}-{slot}')
        players.append(await MatchPlayers.create(match=match, user=user))
    for player, station in zip(players, stations, strict=False):
        player.assigned_station = station
        await player.save()
    return match, players


# ---------------------------------------------------------------------------
# record_match_result — real DB, so the ranks are asserted as persisted.


class TestRecordMatchResult:
    """The contract the one-tap winner buttons in ``MatchResultDialog`` rest on:
    the dialog sends a ``MatchPlayers`` row id and nothing else."""

    @pytest.fixture
    async def actor(self, db):
        return await make_user(discord_id=9101, username='result-staff')

    async def test_record_result_sets_rank_one_and_two_for_two_players(self, db, actor):
        match, players = await _make_onsite_match(seated=True)

        await MatchService().record_match_result(
            match.id, winner_id=players[1].id, actor=actor,
        )

        for player in players:
            await player.refresh_from_db()
        assert players[1].finish_rank == 1
        assert players[0].finish_rank == 2

    async def test_record_result_rejects_a_non_participant_winner(self, db, actor):
        match, players = await _make_onsite_match(seated=True)
        _, other_players = await _make_onsite_match()

        with pytest.raises(ValueError, match="isn't part of this match"):
            await MatchService().record_match_result(
                match.id, winner_id=other_players[0].id, actor=actor,
            )

        for player in players:
            await player.refresh_from_db()
        assert all(p.finish_rank is None for p in players)


class TestReRecordMatchResult:
    """An admin correcting a result the proctor already recorded (T4.2).

    The pencil on a Finished row reaches ``record_match_result`` a second time;
    nothing else in the service changes, so what these pin is that a second call
    is *allowed* and fully rewrites the ranks.
    """

    @pytest.fixture
    async def actor(self, db):
        return await make_user(discord_id=9102, username='correcting-staff')

    async def test_result_can_be_re_recorded_for_a_non_bracket_match(self, db, actor):
        match, players = await _make_onsite_match(finished=True)
        service = MatchService()
        await service.record_match_result(match.id, winner_id=players[0].id, actor=actor)

        await service.record_match_result(match.id, winner_id=players[0].id, actor=actor)

        for player in players:
            await player.refresh_from_db()
        assert players[0].finish_rank == 1
        assert players[1].finish_rank == 2

    async def test_re_recording_swaps_the_ranks(self, db, actor):
        match, players = await _make_onsite_match(finished=True)
        service = MatchService()
        await service.record_match_result(match.id, winner_id=players[0].id, actor=actor)

        await service.record_match_result(match.id, winner_id=players[1].id, actor=actor)

        for player in players:
            await player.refresh_from_db()
        assert players[1].finish_rank == 1
        assert players[0].finish_rank == 2

    async def test_re_recording_a_settled_bracket_game_raises(self, db, actor):
        """The amber toast the UI shows instead of changing the winner.

        ``test_bracket_match_integration`` proves the guard fires off a real
        settled series; this pins that ``record_match_result`` still consults it
        and leaves the recorded ranks alone, since the correction pencil is the
        caller that now hits it most.
        """
        from models import BracketMatchGameState

        match, players = await _make_onsite_match(finished=True)
        service = MatchService()
        await service.record_match_result(match.id, winner_id=players[0].id, actor=actor)

        settled = SimpleNamespace(state=BracketMatchGameState.COMPLETE, bracket_match=None)
        with patch(
            'application.services.bracket_service.BracketService.get_game_for_match',
            AsyncMock(return_value=settled),
        ):
            with pytest.raises(ValueError, match='Correct it from the bracket'):
                await service.record_match_result(
                    match.id, winner_id=players[1].id, actor=actor,
                )

        for player in players:
            await player.refresh_from_db()
        assert players[0].finish_rank == 1
        assert players[1].finish_rank == 2


class TestFlagForReview:
    """The dispute flag (T4.4): a proctor's "an admin should look at this".

    A flag plus a note, never a state — the match stays Finished throughout, and
    these pin the two things that make it trustworthy: it refuses a match that
    was never played out, and it keeps the proctor's own words verbatim.
    """

    @pytest.fixture
    async def actor(self, db):
        return await make_user(discord_id=9103, username='flagging-proctor')

    async def test_flag_for_review_requires_a_finished_match(self, db, actor):
        match, _ = await _make_onsite_match(seated=True)

        with pytest.raises(ValueError, match='Only a finished match'):
            await MatchService().flag_for_review(match.id, 'they disagree', actor)

        await match.refresh_from_db()
        assert match.needs_review is False

    async def test_flag_for_review_stores_the_note(self, db, actor):
        match, _ = await _make_onsite_match(finished=True)

        await MatchService().flag_for_review(
            match.id, '  Timer was still running.  ', actor,
        )

        await match.refresh_from_db()
        assert match.needs_review is True
        assert match.review_note == 'Timer was still running.'

    async def test_flag_for_review_without_a_note_stores_none(self, db, actor):
        """An empty box is no note, not an empty one — the chip renders bare."""
        match, _ = await _make_onsite_match(finished=True)

        await MatchService().flag_for_review(match.id, '   ', actor)

        await match.refresh_from_db()
        assert match.needs_review is True
        assert match.review_note is None

    async def test_flagging_publishes_the_event(self, db, actor, captured_events):
        from application.events import EventType

        match, _ = await _make_onsite_match(finished=True)

        await MatchService().flag_for_review(match.id, 'contested', actor)

        flagged = [e for e in captured_events
                   if e.event_type == EventType.MATCH_FLAGGED_FOR_REVIEW]
        assert len(flagged) == 1
        assert flagged[0].payload['match_id'] == match.id
        assert flagged[0].payload['note'] == 'contested'
        assert flagged[0].payload['tournament_id'] == match.tournament_id

    async def test_clear_review_keeps_the_note(self, db, actor):
        match, _ = await _make_onsite_match(finished=True)
        service = MatchService()
        await service.flag_for_review(match.id, 'Timer was still running.', actor)

        await service.clear_review(match.id, actor)

        await match.refresh_from_db()
        assert match.needs_review is False
        assert match.review_note == 'Timer was still running.'


class TestStationAssignmentValidation:
    """The ``assign_stations`` ladder: duplicate → format → pool → occupancy."""

    @pytest.fixture
    async def actor(self, db):
        return await make_user(discord_id=9001, username='station-staff')

    async def test_rejects_same_station_twice_in_one_match(self, db, actor):
        match, players = await _make_onsite_match()
        with pytest.raises(ValueError, match='more than one player'):
            await MatchService().assign_stations(
                match.id, {players[0].id: '3', players[1].id: '3'}, actor=actor,
            )

    async def test_rejects_station_outside_the_pool(self, db, actor):
        from models import Station

        await Station.create(name='1')
        match, players = await _make_onsite_match()
        with pytest.raises(ValueError, match='not one of'):
            await MatchService().assign_stations(match.id, {players[0].id: '99'}, actor=actor)

    async def test_allows_free_text_when_pool_is_empty(self, db, actor):
        # No Station rows -> historical behaviour, format regex only.
        match, players = await _make_onsite_match()
        await MatchService().assign_stations(match.id, {players[0].id: 'anything'}, actor=actor)
        await players[0].refresh_from_db()
        assert players[0].assigned_station == 'anything'

    async def test_rejects_station_in_use_by_a_live_match(self, db, actor):
        """And names the match sitting there, rather than quoting its id.

        The proctor's next move is to go and find those players; "match #23"
        is the one thing that does not help them do it.
        """
        from models import Station

        await Station.create(name='4')
        other, other_players = await _make_onsite_match(seated=True, stations=('4',))
        match, players = await _make_onsite_match()
        with pytest.raises(ValueError) as exc:
            await MatchService().assign_stations(match.id, {players[0].id: '4'}, actor=actor)
        message = str(exc.value)
        assert f'#{other.id}' not in message
        for player in other_players:
            assert (await player.user).preferred_name in message

    async def test_frees_the_station_once_the_other_match_finishes(self, db, actor):
        from models import Station

        await Station.create(name='4')
        await _make_onsite_match(seated=True, finished=True, stations=('4',))
        match, players = await _make_onsite_match()
        await MatchService().assign_stations(match.id, {players[0].id: '4'}, actor=actor)
        await players[0].refresh_from_db()
        assert players[0].assigned_station == '4'

    async def test_reassigning_a_match_to_its_own_station_is_allowed(self, db, actor):
        # exclude_match_id must not make a match collide with itself.
        from models import Station

        for name in ('4', '5'):
            await Station.create(name=name)
        match, players = await _make_onsite_match()
        match.seated_at = datetime(2025, 1, 15, 19, 0)
        await match.save()
        await MatchService().assign_stations(match.id, {players[0].id: '4'}, actor=actor)
        await MatchService().assign_stations(
            match.id, {players[0].id: '4', players[1].id: '5'}, actor=actor,
        )
        await players[1].refresh_from_db()
        assert players[1].assigned_station == '5'
