from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.services.match_service import MatchService


@pytest.fixture(autouse=True)
def bypass_auth(monkeypatch):
    """Disable AuthService permission checks for tests; they exercise business logic."""
    from application.services import auth_service

    async def allow(*_args, **_kwargs):
        return True

    async def noop_ensure(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth_service.AuthService, 'can_transition_match', allow)
    monkeypatch.setattr(auth_service.AuthService, 'can_crud_match', allow)
    monkeypatch.setattr(auth_service.AuthService, 'can_assign_match_stream', allow)
    monkeypatch.setattr(auth_service.AuthService, 'is_staff', allow)
    monkeypatch.setattr(auth_service.AuthService, 'is_tournament_admin', allow)
    monkeypatch.setattr(auth_service.AuthService, 'ensure', noop_ensure)


@pytest.fixture
def service():
    svc = object.__new__(MatchService)
    svc.repository = MagicMock()
    svc.stream_room_repository = MagicMock()
    svc.tournament_repository = MagicMock()
    svc.user_repository = MagicMock()
    svc.commentator_repository = MagicMock()
    svc.tracker_repository = MagicMock()
    svc.ack_repository = MagicMock()
    svc.ack_repository.delete_for_match = AsyncMock()
    svc.ack_repository.upsert = AsyncMock()
    svc.ack_repository.list_for_match = AsyncMock(return_value=[])
    svc.ack_repository.list_for_matches = AsyncMock(return_value={})
    svc.ack_repository.get = AsyncMock(return_value=None)
    svc.audit_service = MagicMock()
    svc.audit_service.write_log = AsyncMock()
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
        scheduled_at=datetime(2025, 1, 15, 19, 30),
        comment=None,
        tournament=SimpleNamespace(name="Test Tournament", seed_generator=None),
        stream_room=None,
        stream_room_id=None,
        generated_seed=None,
        is_stream_candidate=False,
        players=[],
        commentators=[],
        trackers=[],
        fetch_related=AsyncMock(),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# _get_match_state
# ---------------------------------------------------------------------------


class TestGetMatchState:
    def test_scheduled_when_no_timestamps(self, service):
        assert service._get_match_state(make_match()) == "Scheduled"

    def test_checked_in_when_only_seated(self, service):
        match = make_match(seated_at=datetime.now())
        assert service._get_match_state(match) == "Checked In"

    def test_started_when_seated_and_started(self, service):
        now = datetime.now()
        match = make_match(seated_at=now, started_at=now)
        assert service._get_match_state(match) == "Started"

    def test_finished_when_finished_set(self, service):
        now = datetime.now()
        match = make_match(seated_at=now, started_at=now, finished_at=now)
        assert service._get_match_state(match) == "Finished"

    def test_confirmed_takes_highest_priority(self, service):
        now = datetime.now()
        match = make_match(seated_at=now, started_at=now, finished_at=now, confirmed_at=now)
        assert service._get_match_state(match) == "Confirmed"

    def test_confirmed_beats_finished(self, service):
        now = datetime.now()
        # Even without started_at, confirmed_at should dominate
        match = make_match(finished_at=now, confirmed_at=now)
        assert service._get_match_state(match) == "Confirmed"


# ---------------------------------------------------------------------------
# _format_match_for_display
# ---------------------------------------------------------------------------


class TestFormatMatchForDisplay:
    def test_returns_id(self, service):
        result = service._format_match_for_display(make_match(id=77))
        assert result["id"] == 77

    def test_state_is_scheduled_by_default(self, service):
        result = service._format_match_for_display(make_match())
        assert result["state"] == "Scheduled"

    def test_state_timestamp_is_none_when_scheduled(self, service):
        result = service._format_match_for_display(make_match())
        assert result["state_timestamp"] is None

    def test_stream_room_empty_when_none(self, service):
        result = service._format_match_for_display(make_match(stream_room=None))
        assert result["stream_room"] == ""

    def test_stream_room_name_when_set(self, service):
        match = make_match(stream_room=SimpleNamespace(name="Stage 1", stream_url="https://twitch.tv/sglive1"))
        result = service._format_match_for_display(match)
        assert result["stream_room"] == "Stage 1"
        assert result["stream_room_url"] == "https://twitch.tv/sglive1"

    def test_stream_room_url_empty_when_none(self, service):
        result = service._format_match_for_display(make_match(stream_room=None))
        assert result["stream_room_url"] == ""

    def test_stream_room_url_empty_for_invalid_scheme(self, service):
        match = make_match(stream_room=SimpleNamespace(name="Stage 1", stream_url="javascript:alert(1)"))
        result = service._format_match_for_display(match)
        assert result["stream_room_url"] == ""

    def test_seed_empty_when_none(self, service):
        result = service._format_match_for_display(make_match(generated_seed=None))
        assert result["seed"] == ""

    def test_seed_url_when_set(self, service):
        match = make_match(generated_seed=SimpleNamespace(seed_url="https://alttpr.com/h/abc"))
        result = service._format_match_for_display(match)
        assert result["seed"] == "https://alttpr.com/h/abc"

    def test_tournament_name_in_result(self, service):
        result = service._format_match_for_display(make_match())
        assert result["tournament"] == "Test Tournament"

    def test_tournament_empty_when_none(self, service):
        match = make_match(tournament=None)
        result = service._format_match_for_display(match)
        assert result["tournament"] == ""

    def test_players_formatted_as_tuples(self, service):
        player = SimpleNamespace(
            user=SimpleNamespace(preferred_name="Alice"),
            finish_rank=1,
            assigned_station="A",
        )
        result = service._format_match_for_display(make_match(players=[player]))
        assert result["players"] == [("Alice", 1, "A")]

    def test_multiple_players_all_included(self, service):
        players = [
            SimpleNamespace(user=SimpleNamespace(preferred_name="Alice"), finish_rank=1, assigned_station="A"),
            SimpleNamespace(user=SimpleNamespace(preferred_name="Bob"), finish_rank=2, assigned_station="B"),
        ]
        result = service._format_match_for_display(make_match(players=players))
        assert len(result["players"]) == 2

    def test_commentators_formatted_as_tuples(self, service):
        commentator = SimpleNamespace(
            id=11,
            user=SimpleNamespace(preferred_name="Charlie", discord_id="123"),
            approved=True,
            acknowledged_at=None,
            auto_acknowledged=False,
        )
        result = service._format_match_for_display(make_match(commentators=[commentator]))
        assert result["commentators"] == [("Charlie", True, "123", False, "", 11)]

    def test_trackers_formatted_as_tuples(self, service):
        tracker = SimpleNamespace(
            id=22,
            user=SimpleNamespace(preferred_name="Dana", discord_id="456"),
            approved=False,
            acknowledged_at=None,
            auto_acknowledged=False,
        )
        result = service._format_match_for_display(make_match(trackers=[tracker]))
        assert result["trackers"] == [("Dana", False, "456", False, "", 22)]

    def test_state_timestamp_set_when_seated(self, service):
        match = make_match(seated_at=datetime(2025, 1, 15, 19, 30))
        result = service._format_match_for_display(match)
        assert result["state_timestamp"] is not None

    def test_state_timestamp_reflects_highest_state(self, service):
        now = datetime.now()
        match = make_match(seated_at=now, started_at=now, finished_at=now, confirmed_at=now)
        result = service._format_match_for_display(match)
        assert result["state"] == "Confirmed"
        assert result["state_timestamp"] is not None

    def test_scheduled_at_formatted_as_string(self, service):
        match = make_match(scheduled_at=datetime(2025, 1, 15, 19, 30))
        result = service._format_match_for_display(match)
        assert isinstance(result["scheduled_at"], str)
        assert result["scheduled_at"] != ""

    def test_scheduled_at_empty_when_none(self, service):
        match = make_match(scheduled_at=None)
        result = service._format_match_for_display(match)
        assert result["scheduled_at"] == ""


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


# ---------------------------------------------------------------------------
# signup_crew
# ---------------------------------------------------------------------------


class TestSignupCrew:
    async def test_raises_for_invalid_role(self, service):
        with pytest.raises(ValueError, match="Invalid role"):
            await service.signup_crew(match_id=1, user=MagicMock(), role="referee")

    async def test_raises_when_match_not_found(self, service):
        service.repository.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="not found"):
            await service.signup_crew(match_id=999, user=MagicMock(), role="commentator")

    async def test_raises_when_commentator_already_signed_up(self, service):
        user = SimpleNamespace(id=42)
        match = make_match(commentators=[SimpleNamespace(user_id=42)])
        service.repository.get_by_id = AsyncMock(return_value=match)
        with pytest.raises(ValueError, match="already signed up"):
            await service.signup_crew(match_id=1, user=user, role="commentator")

    async def test_raises_when_tracker_already_signed_up(self, service):
        user = SimpleNamespace(id=42)
        match = make_match(trackers=[SimpleNamespace(user_id=42)])
        service.repository.get_by_id = AsyncMock(return_value=match)
        with pytest.raises(ValueError, match="already signed up"):
            await service.signup_crew(match_id=1, user=user, role="tracker")

    async def test_creates_commentator_when_valid(self, service):
        user = SimpleNamespace(id=99)
        match = make_match(commentators=[])
        service.repository.get_by_id = AsyncMock(return_value=match)
        service.commentator_repository.create = AsyncMock()
        await service.signup_crew(match_id=1, user=user, role="commentator")
        service.commentator_repository.create.assert_awaited_once_with(
            match=match, user=user, approved=False
        )

    async def test_creates_tracker_when_valid(self, service):
        user = SimpleNamespace(id=99)
        match = make_match(trackers=[])
        service.repository.get_by_id = AsyncMock(return_value=match)
        service.tracker_repository.create = AsyncMock()
        await service.signup_crew(match_id=1, user=user, role="tracker")
        service.tracker_repository.create.assert_awaited_once_with(
            match=match, user=user, approved=False
        )

    async def test_invalid_role_check_precedes_db_lookup(self, service):
        service.repository.get_by_id = AsyncMock()
        with pytest.raises(ValueError, match="Invalid role"):
            await service.signup_crew(match_id=1, user=MagicMock(), role="judge")
        service.repository.get_by_id.assert_not_awaited()


# ---------------------------------------------------------------------------
# undo_crew_signup
# ---------------------------------------------------------------------------


class TestUndoCrewSignup:
    async def test_raises_for_invalid_role(self, service):
        with pytest.raises(ValueError, match="Invalid role"):
            await service.undo_crew_signup(match_id=1, user=MagicMock(), role="referee")

    async def test_raises_when_match_not_found(self, service):
        service.repository.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="not found"):
            await service.undo_crew_signup(match_id=999, user=MagicMock(), role="commentator")

    async def test_raises_when_commentator_not_signed_up(self, service):
        user = SimpleNamespace(id=42)
        match = make_match(commentators=[])
        service.repository.get_by_id = AsyncMock(return_value=match)
        with pytest.raises(ValueError, match="not signed up"):
            await service.undo_crew_signup(match_id=1, user=user, role="commentator")

    async def test_raises_when_tracker_not_signed_up(self, service):
        user = SimpleNamespace(id=42)
        match = make_match(trackers=[])
        service.repository.get_by_id = AsyncMock(return_value=match)
        with pytest.raises(ValueError, match="not signed up"):
            await service.undo_crew_signup(match_id=1, user=user, role="tracker")

    async def test_deletes_commentator_when_found(self, service):
        user = SimpleNamespace(id=42)
        crew_member = SimpleNamespace(user_id=42, delete=AsyncMock())
        match = make_match(commentators=[crew_member])
        service.repository.get_by_id = AsyncMock(return_value=match)
        await service.undo_crew_signup(match_id=1, user=user, role="commentator")
        crew_member.delete.assert_awaited_once()

    async def test_deletes_tracker_when_found(self, service):
        user = SimpleNamespace(id=42)
        crew_member = SimpleNamespace(user_id=42, delete=AsyncMock())
        match = make_match(trackers=[crew_member])
        service.repository.get_by_id = AsyncMock(return_value=match)
        await service.undo_crew_signup(match_id=1, user=user, role="tracker")
        crew_member.delete.assert_awaited_once()

    async def test_invalid_role_check_precedes_db_lookup(self, service):
        service.repository.get_by_id = AsyncMock()
        with pytest.raises(ValueError, match="Invalid role"):
            await service.undo_crew_signup(match_id=1, user=MagicMock(), role="judge")
        service.repository.get_by_id.assert_not_awaited()


# ---------------------------------------------------------------------------
# finish_match (MatchService, not MatchScheduleService)
# ---------------------------------------------------------------------------


class TestMatchServiceFinishMatch:
    async def test_raises_when_match_not_found(self, service):
        service.repository.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="not found"):
            await service.finish_match(match_id=999)

    async def test_raises_when_not_seated(self, service):
        match = make_match(seated_at=None)
        service.repository.get_by_id = AsyncMock(return_value=match)
        with pytest.raises(ValueError, match="hasn't been seated"):
            await service.finish_match(match_id=1)

    async def test_updates_finished_at(self, service):
        match = make_match(seated_at=datetime.now())
        service.repository.get_by_id = AsyncMock(return_value=match)
        service.repository.update = AsyncMock(return_value=match)
        await service.finish_match(match_id=1)
        call_kwargs = service.repository.update.call_args
        assert "finished_at" in call_kwargs.kwargs


# ---------------------------------------------------------------------------
# _format_match_for_display — is_stream_candidate field
# ---------------------------------------------------------------------------


class TestFormatMatchIsStreamCandidate:
    def test_is_stream_candidate_false_by_default(self, service):
        result = service._format_match_for_display(make_match())
        assert result["is_stream_candidate"] is False

    def test_is_stream_candidate_true_when_set(self, service):
        result = service._format_match_for_display(make_match(is_stream_candidate=True))
        assert result["is_stream_candidate"] is True


# ---------------------------------------------------------------------------
# create_match — subscriber notification fan-out
# ---------------------------------------------------------------------------


def _setup_create_match_mocks(service):
    """Wire up minimal mocks to let create_match reach its notification phase."""
    user = SimpleNamespace(id=1, discord_id=111)
    match = make_match(id=1, tournament_id=1, is_stream_candidate=False)

    service.repository.create = AsyncMock(return_value=match)
    service.user_repository.get_by_id = AsyncMock(return_value=user)
    service.tournament_repository.is_player_enrolled_by_id = AsyncMock(return_value=True)
    service.repository.add_player = AsyncMock()

    service.match_schedule_service._create_scheduled_dm_message = MagicMock(return_value="scheduled msg")
    service.match_schedule_service.notify_match_participants = AsyncMock()
    service.match_schedule_service.notify_tournament_subscribers_scheduled = AsyncMock()
    service.match_schedule_service.notify_stream_candidate_subscribers = AsyncMock()

    # Avoid real ORM queries in _collect_notified_discord_ids
    service._collect_notified_discord_ids = AsyncMock(return_value=[111])

    return match, user


class TestCreateMatchSubscriberNotifications:
    async def test_tournament_subscriber_notification_called(self, service):
        match, _ = _setup_create_match_mocks(service)
        await service.create_match(
            tournament_id=1,
            scheduled_date="2025-01-15",
            scheduled_time="14:30",
            player_ids=[1],
        )
        service.match_schedule_service.notify_tournament_subscribers_scheduled.assert_called_once()

    async def test_stream_candidate_notification_not_called_when_flag_false(self, service):
        _setup_create_match_mocks(service)
        await service.create_match(
            tournament_id=1,
            scheduled_date="2025-01-15",
            scheduled_time="14:30",
            player_ids=[1],
            is_stream_candidate=False,
        )
        service.match_schedule_service.notify_stream_candidate_subscribers.assert_not_called()

    async def test_stream_candidate_notification_called_when_flag_true(self, service):
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
        service.match_schedule_service.notify_stream_candidate_subscribers.assert_called_once()

    async def test_subscriber_notification_receives_excluded_ids(self, service):
        _setup_create_match_mocks(service)
        service._collect_notified_discord_ids = AsyncMock(return_value=[111, 222])
        await service.create_match(
            tournament_id=1,
            scheduled_date="2025-01-15",
            scheduled_time="14:30",
            player_ids=[1],
        )
        call_args = service.match_schedule_service.notify_tournament_subscribers_scheduled.call_args
        # Third positional arg is exclude_discord_ids
        exclude_ids = call_args.args[2]
        assert 111 in exclude_ids
        assert 222 in exclude_ids


# ---------------------------------------------------------------------------
# Acknowledgment seeding / acknowledge_match
# ---------------------------------------------------------------------------


class TestSeedAcknowledgments:
    async def test_actor_auto_acked_when_in_player_list(self, service):
        actor = SimpleNamespace(id=42)
        user = SimpleNamespace(id=42)
        service.user_repository.get_by_id = AsyncMock(return_value=user)
        match = make_match()
        await service._seed_acknowledgments(match, [42], actor)
        service.ack_repository.delete_for_match.assert_awaited_once_with(match)
        call = service.ack_repository.upsert.await_args
        assert call.kwargs["acknowledged"] is True
        assert call.kwargs["auto"] is True

    async def test_non_actor_left_pending(self, service):
        actor = SimpleNamespace(id=42)
        opponent = SimpleNamespace(id=99)
        service.user_repository.get_by_id = AsyncMock(return_value=opponent)
        match = make_match()
        await service._seed_acknowledgments(match, [99], actor)
        call = service.ack_repository.upsert.await_args
        assert call.kwargs["acknowledged"] is False
        assert call.kwargs["auto"] is False

    async def test_no_actor_means_no_auto_ack(self, service):
        user = SimpleNamespace(id=99)
        service.user_repository.get_by_id = AsyncMock(return_value=user)
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
