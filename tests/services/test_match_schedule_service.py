from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.match_schedule_service import MatchScheduleService
from application.utils.discord_messages import (
    checked_in_dm,
    scheduled_dm,
    seed_dm,
    state_changed_dm,
    stream_candidate_dm,
    _players_label,
)


class TestPlayersLabel:
    def test_two_players_uses_vs(self):
        assert _players_label(["Alice", "Bob"]) == "Alice vs Bob"

    def test_three_players_comma_joined(self):
        assert _players_label(["A", "B", "C"]) == "A, B, C"

    def test_empty_returns_blank(self):
        assert _players_label(None) == ""
        assert _players_label([]) == ""


class TestMatchInfoBlock:
    def test_stage_omitted_when_no_stream_room(self):
        msg = scheduled_dm(
            "Test", "2025-01-15 14:30 EST", player_names=["Alice", "Bob"]
        )
        assert "Stage:" not in msg
        assert "Players: Alice vs Bob" in msg

    def test_stage_included_when_assigned(self):
        msg = scheduled_dm(
            "Test", "2025-01-15 14:30 EST",
            player_names=["Alice", "Bob"], stream_room_name="Stage 1",
        )
        assert "Stage: Stage 1" in msg

    def test_state_changed_has_no_match_id(self):
        msg = state_changed_dm("Test", "Started", player_names=["Alice", "Bob"])
        assert "Match ID" not in msg
        assert "Alice vs Bob" in msg

    def test_checked_in_has_no_match_id(self):
        msg = checked_in_dm("Test", player_names=["Alice", "Bob"])
        assert "Match ID" not in msg
        assert "Alice vs Bob" in msg


class MockTournament:
    def __init__(self, name="Test Tournament", is_racetime_enabled=False):
        self.name = name
        self.is_racetime_enabled = is_racetime_enabled


class MockMatch:
    """Minimal stand-in for a Match ORM object."""

    def __init__(self, *, seated_at=None, started_at=None, finished_at=None,
                 confirmed_at=None, id=1, stream_room_id=None, tournament_id=1,
                 scheduled_at=None, players=None, stream_room=None,
                 is_racetime_enabled=False):
        self.id = id
        self.seated_at = seated_at
        self.started_at = started_at
        self.finished_at = finished_at
        self.confirmed_at = confirmed_at
        self.stream_room_id = stream_room_id
        self.tournament_id = tournament_id
        self.scheduled_at = scheduled_at or datetime(2025, 1, 15, 19, 30)
        self.tournament = MockTournament(is_racetime_enabled=is_racetime_enabled)
        self.players = players if players is not None else []
        self.stream_room = stream_room
        self.save = AsyncMock()
        self.fetch_related = AsyncMock()


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
    monkeypatch.setattr(auth_service.AuthService, 'ensure', noop_ensure)


@pytest.fixture
def service():
    svc = object.__new__(MatchScheduleService)
    svc.match_repository = MagicMock()
    svc.discord_service = MagicMock()
    svc.seedgen_service = MagicMock()
    svc._seed_locks = {}
    svc.audit_service = MagicMock()
    svc.audit_service.write_log = AsyncMock()
    svc.notify_match_participants = AsyncMock()
    return svc


class TestSeatMatch:
    async def test_sets_seated_at(self, service):
        match = MockMatch()
        await service.seat_match(match)
        assert match.seated_at is not None

    async def test_persists_the_change(self, service):
        match = MockMatch()
        await service.seat_match(match)
        match.save.assert_awaited_once()

    async def test_seated_at_is_recent(self, service):
        match = MockMatch()
        before = datetime.now(timezone.utc)
        await service.seat_match(match)
        after = datetime.now(timezone.utc)
        assert before <= match.seated_at <= after

    async def test_raises_if_already_seated(self, service):
        match = MockMatch(seated_at=datetime.now())
        with pytest.raises(ValueError, match="already checked in"):
            await service.seat_match(match)

    async def test_does_not_save_on_error(self, service):
        match = MockMatch(seated_at=datetime.now())
        with pytest.raises(ValueError):
            await service.seat_match(match)
        match.save.assert_not_awaited()

    async def test_racetime_tournament_rejects_check_in(self, service):
        match = MockMatch(is_racetime_enabled=True)
        with pytest.raises(ValueError, match="racetime.gg"):
            await service.seat_match(match)

    async def test_racetime_tournament_does_not_seat(self, service):
        match = MockMatch(is_racetime_enabled=True)
        with pytest.raises(ValueError):
            await service.seat_match(match)
        assert match.seated_at is None
        match.save.assert_not_awaited()


class TestStartMatch:
    async def test_sets_started_at(self, service):
        match = MockMatch(seated_at=datetime.now())
        await service.start_match(match)
        assert match.started_at is not None

    async def test_persists_the_change(self, service):
        match = MockMatch(seated_at=datetime.now())
        await service.start_match(match)
        match.save.assert_awaited_once()

    async def test_raises_if_not_seated(self, service):
        match = MockMatch()
        with pytest.raises(ValueError, match="checked in before starting"):
            await service.start_match(match)

    async def test_raises_if_already_started(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now)
        with pytest.raises(ValueError, match="already started"):
            await service.start_match(match)

    async def test_does_not_modify_seated_at(self, service):
        seated = datetime(2025, 1, 15, 10, 0)
        match = MockMatch(seated_at=seated)
        await service.start_match(match)
        assert match.seated_at == seated


class TestFinishMatch:
    async def test_sets_finished_at(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now)
        await service.finish_match(match)
        assert match.finished_at is not None

    async def test_persists_the_change(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now)
        await service.finish_match(match)
        match.save.assert_awaited_once()

    async def test_raises_if_not_started(self, service):
        match = MockMatch()
        with pytest.raises(ValueError, match="started before finishing"):
            await service.finish_match(match)

    async def test_raises_if_already_finished(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now, finished_at=now)
        with pytest.raises(ValueError, match="already finished"):
            await service.finish_match(match)

    async def test_does_not_require_confirmed_at_to_be_none(self, service):
        # confirmed_at is irrelevant to finish check
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now)
        await service.finish_match(match)
        assert match.finished_at is not None


class TestConfirmMatch:
    async def test_sets_confirmed_at(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now, finished_at=now)
        await service.confirm_match(match)
        assert match.confirmed_at is not None

    async def test_persists_the_change(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now, finished_at=now)
        await service.confirm_match(match)
        match.save.assert_awaited_once()

    async def test_raises_if_not_finished(self, service):
        match = MockMatch()
        with pytest.raises(ValueError, match="finished before confirming"):
            await service.confirm_match(match)

    async def test_raises_if_already_confirmed(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now, finished_at=now, confirmed_at=now)
        with pytest.raises(ValueError, match="already confirmed"):
            await service.confirm_match(match)


class TestFullLifecycle:
    async def test_seat_start_finish_confirm_in_order(self, service):
        match = MockMatch()
        await service.seat_match(match)
        await service.start_match(match)
        await service.finish_match(match)
        await service.confirm_match(match)
        assert match.confirmed_at is not None
        assert match.save.await_count == 4

    async def test_cannot_skip_seat_to_start(self, service):
        match = MockMatch()
        with pytest.raises(ValueError):
            await service.start_match(match)

    async def test_cannot_skip_start_to_finish(self, service):
        match = MockMatch(seated_at=datetime.now())
        with pytest.raises(ValueError):
            await service.finish_match(match)

    async def test_cannot_skip_finish_to_confirm(self, service):
        now = datetime.now()
        match = MockMatch(seated_at=now, started_at=now)
        with pytest.raises(ValueError):
            await service.confirm_match(match)


class TestStreamCandidateDm:
    def test_contains_player_names(self):
        msg = stream_candidate_dm(
            "ALttPR Open", "2025-01-15 14:30 EST", player_names=["Alice", "Bob"]
        )
        assert "Alice vs Bob" in msg

    def test_omits_match_id(self):
        msg = stream_candidate_dm(
            "ALttPR Open", "2025-01-15 14:30 EST", player_names=["Alice", "Bob"]
        )
        assert "Match ID" not in msg

    def test_contains_tournament_name(self):
        msg = stream_candidate_dm("ALttPR Open", "2025-01-15 14:30 EST")
        assert "ALttPR Open" in msg

    def test_contains_scheduled_at(self):
        msg = stream_candidate_dm("Test", "2025-01-15 14:30 EST")
        assert "2025-01-15 14:30 EST" in msg

    def test_is_non_empty_string(self):
        msg = stream_candidate_dm("Test", "")
        assert isinstance(msg, str)
        assert len(msg) > 0


class TestNotifyTournamentSubscribersScheduled:
    async def test_sends_dm_with_crew_buttons_to_qualifying_subscriber(self, service):
        match = MockMatch()
        subscriber = SimpleNamespace(discord_id=999)
        mock_repo = MagicMock()
        mock_repo.get_match_notification_subscribers = AsyncMock(return_value=[subscriber])
        service.discord_service.send_dm_with_crew_buttons = AsyncMock(return_value=(True, "ok"))

        with patch('application.repositories.TournamentNotificationRepository', return_value=mock_repo):
            await service.notify_tournament_subscribers_scheduled(match, "msg", [])

        service.discord_service.send_dm_with_crew_buttons.assert_awaited_once_with(999, "msg", match.id)

    async def test_excludes_already_notified_discord_ids(self, service):
        match = MockMatch()
        subscriber = SimpleNamespace(discord_id=999)
        mock_repo = MagicMock()
        mock_repo.get_match_notification_subscribers = AsyncMock(return_value=[subscriber])
        service.discord_service.send_dm_with_crew_buttons = AsyncMock(return_value=(True, "ok"))

        with patch('application.repositories.TournamentNotificationRepository', return_value=mock_repo):
            await service.notify_tournament_subscribers_scheduled(match, "msg", [999])

        service.discord_service.send_dm_with_crew_buttons.assert_not_awaited()

    async def test_passes_has_stream_room_true_when_set(self, service):
        match = MockMatch(stream_room_id=5)
        mock_repo = MagicMock()
        mock_repo.get_match_notification_subscribers = AsyncMock(return_value=[])
        service.discord_service.send_dm_with_crew_buttons = AsyncMock()

        with patch('application.repositories.TournamentNotificationRepository', return_value=mock_repo):
            await service.notify_tournament_subscribers_scheduled(match, "msg", [])

        mock_repo.get_match_notification_subscribers.assert_awaited_once_with(
            match.tournament_id, has_stream_room=True
        )

    async def test_passes_has_stream_room_false_when_not_set(self, service):
        match = MockMatch(stream_room_id=None)
        mock_repo = MagicMock()
        mock_repo.get_match_notification_subscribers = AsyncMock(return_value=[])
        service.discord_service.send_dm_with_crew_buttons = AsyncMock()

        with patch('application.repositories.TournamentNotificationRepository', return_value=mock_repo):
            await service.notify_tournament_subscribers_scheduled(match, "msg", [])

        mock_repo.get_match_notification_subscribers.assert_awaited_once_with(
            match.tournament_id, has_stream_room=False
        )

    async def test_swallows_exception_without_raising(self, service):
        match = MockMatch()
        with patch('application.repositories.TournamentNotificationRepository', side_effect=Exception("db error")):
            # Should not raise
            await service.notify_tournament_subscribers_scheduled(match, "msg", [])


class TestNotifyStreamCandidateSubscribers:
    async def test_skips_entirely_when_match_has_stream_room(self, service):
        match = MockMatch(stream_room_id=3)
        mock_repo = MagicMock()
        mock_repo.get_stream_candidate_subscribers = AsyncMock(return_value=[])
        service.discord_service.send_dm_with_crew_buttons = AsyncMock()

        with patch('application.repositories.TournamentNotificationRepository', return_value=mock_repo):
            await service.notify_stream_candidate_subscribers(match, [])

        mock_repo.get_stream_candidate_subscribers.assert_not_awaited()
        service.discord_service.send_dm_with_crew_buttons.assert_not_awaited()

    async def test_sends_dm_to_subscriber_when_no_stream_room(self, service):
        match = MockMatch(stream_room_id=None)
        subscriber = SimpleNamespace(discord_id=777)
        mock_repo = MagicMock()
        mock_repo.get_stream_candidate_subscribers = AsyncMock(return_value=[subscriber])
        service.discord_service.send_dm_with_crew_buttons = AsyncMock(return_value=(True, "ok"))

        with patch('application.repositories.TournamentNotificationRepository', return_value=mock_repo):
            await service.notify_stream_candidate_subscribers(match, [])

        service.discord_service.send_dm_with_crew_buttons.assert_awaited_once()
        call_args = service.discord_service.send_dm_with_crew_buttons.call_args
        assert call_args.args[0] == 777

    async def test_excludes_already_notified_discord_ids(self, service):
        match = MockMatch(stream_room_id=None)
        subscriber = SimpleNamespace(discord_id=777)
        mock_repo = MagicMock()
        mock_repo.get_stream_candidate_subscribers = AsyncMock(return_value=[subscriber])
        service.discord_service.send_dm_with_crew_buttons = AsyncMock(return_value=(True, "ok"))

        with patch('application.repositories.TournamentNotificationRepository', return_value=mock_repo):
            await service.notify_stream_candidate_subscribers(match, [777])

        service.discord_service.send_dm_with_crew_buttons.assert_not_awaited()

    async def test_swallows_exception_without_raising(self, service):
        match = MockMatch(stream_room_id=None)
        with patch('application.repositories.TournamentNotificationRepository', side_effect=Exception("db error")):
            await service.notify_stream_candidate_subscribers(match, [])


class TestNotifyMatchScheduled:
    """The collapsed scheduled/rescheduled fan-out shared by create/update/request."""

    @staticmethod
    def _wire(service):
        # Sub-notifications are passed to the queue (never awaited here), so plain
        # MagicMocks avoid 'coroutine never awaited' noise; _collect is awaited.
        service.notify_acknowledgment_request = MagicMock()
        service.notify_match_crew = MagicMock()
        service.notify_tournament_subscribers_scheduled = MagicMock()
        service.notify_stream_candidate_subscribers = MagicMock()
        service._collect_notified_discord_ids = AsyncMock(return_value=[111])

    async def test_enqueues_ack_crew_and_subscribers(self, service):
        self._wire(service)
        match = MockMatch()
        with patch('application.services.match_schedule_service.discord_queue.enqueue') as enqueue:
            await service.notify_match_scheduled(match, rescheduled=False, is_stream_candidate=False)

        _, ack_kwargs = service.notify_acknowledgment_request.call_args
        assert ack_kwargs == {'rescheduled': False}
        subs_args = service.notify_tournament_subscribers_scheduled.call_args.args
        assert subs_args[0] is match
        assert subs_args[2] == [111]
        service.notify_stream_candidate_subscribers.assert_not_called()
        assert enqueue.call_count == 3

    async def test_stream_candidate_enqueued_when_flagged(self, service):
        self._wire(service)
        match = MockMatch()
        with patch('application.services.match_schedule_service.discord_queue.enqueue') as enqueue:
            await service.notify_match_scheduled(match, rescheduled=False, is_stream_candidate=True)

        candidate_args = service.notify_stream_candidate_subscribers.call_args.args
        assert candidate_args[0] is match
        assert candidate_args[1] == [111]
        assert enqueue.call_count == 4

    async def test_rescheduled_flag_forwarded_to_ack_request(self, service):
        self._wire(service)
        match = MockMatch()
        with patch('application.services.match_schedule_service.discord_queue.enqueue'):
            await service.notify_match_scheduled(match, rescheduled=True)

        _, ack_kwargs = service.notify_acknowledgment_request.call_args
        assert ack_kwargs == {'rescheduled': True}


class TestNotifyStreamCandidate:
    async def test_enqueues_stream_candidate_subscribers(self, service):
        service.notify_stream_candidate_subscribers = MagicMock()
        service._collect_notified_discord_ids = AsyncMock(return_value=[111, 222])
        match = MockMatch()
        with patch('application.services.match_schedule_service.discord_queue.enqueue') as enqueue:
            await service.notify_stream_candidate(match)

        args = service.notify_stream_candidate_subscribers.call_args.args
        assert args[0] is match
        assert args[1] == [111, 222]
        assert enqueue.call_count == 1


class TestCollectNotifiedDiscordIds:
    @staticmethod
    def _patch_query(target, rows):
        mock_qs = MagicMock()
        mock_qs.prefetch_related = MagicMock(return_value=AsyncMock(return_value=rows)())
        return patch(target, return_value=mock_qs)

    async def test_dedupes_players_and_approved_crew(self, service):
        match = MockMatch()
        player = SimpleNamespace(user=SimpleNamespace(discord_id=111))
        commentator = SimpleNamespace(user=SimpleNamespace(discord_id=222))
        # Tracker shares the commentator's id — should be deduped away.
        tracker = SimpleNamespace(user=SimpleNamespace(discord_id=222))

        with self._patch_query('application.services.match_schedule_service.MatchPlayers.filter', [player]), \
             self._patch_query('application.services.match_schedule_service.Commentator.filter', [commentator]), \
             self._patch_query('application.services.match_schedule_service.Tracker.filter', [tracker]):
            ids = await service._collect_notified_discord_ids(match)

        assert ids == [111, 222]


class TestSeedDm:
    def test_contains_player_name(self):
        msg = seed_dm("Alice", "ALttPR Open", "https://alttpr.com/h/abc")
        assert "Alice" in msg

    def test_omits_match_id(self):
        msg = seed_dm(
            "Alice", "ALttPR Open", "https://alttpr.com/h/abc",
            player_names=["Alice", "Bob"],
        )
        assert "Match ID" not in msg
        assert "ID:" not in msg

    def test_contains_player_names_block(self):
        msg = seed_dm(
            "Alice", "ALttPR Open", "https://alttpr.com/h/abc",
            player_names=["Alice", "Bob"],
        )
        assert "Alice vs Bob" in msg

    def test_contains_tournament_name(self):
        msg = seed_dm("Alice", "ALttPR Open", "https://alttpr.com/h/abc")
        assert "ALttPR Open" in msg

    def test_contains_seed_url(self):
        url = "https://alttpr.com/h/abc123"
        msg = seed_dm("Alice", "ALttPR Open", url)
        assert url in msg

    def test_is_non_empty_string(self):
        msg = seed_dm("Bob", "OoTR", "https://ootrandomizer.com/seed/1")
        assert isinstance(msg, str)
        assert len(msg) > 0


class TestNotifyMatchParticipants:
    @pytest.fixture
    def real_notify_service(self, service):
        del service.notify_match_participants
        service.discord_service.send_dm = AsyncMock(return_value=(True, "ok"))
        service.discord_service.send_dm_with_unwatch_button = AsyncMock(return_value=(True, "ok"))
        return service

    @staticmethod
    def _patch_query(target, rows):
        mock_qs = MagicMock()
        mock_qs.prefetch_related = MagicMock(return_value=AsyncMock(return_value=rows)())
        return patch(target, return_value=mock_qs)

    async def test_player_only_gets_plain_dm(self, real_notify_service):
        match = MockMatch()
        player = SimpleNamespace(user=SimpleNamespace(discord_id=111, dm_notifications=True))

        with self._patch_query('application.services.match_schedule_service.MatchPlayers.filter', [player]), \
             self._patch_query('application.services.match_schedule_service.Commentator.filter', []), \
             self._patch_query('application.services.match_schedule_service.Tracker.filter', []), \
             self._patch_query('application.services.match_schedule_service.MatchWatcher.filter', []):
            await real_notify_service.notify_match_participants(match, "hello")

        real_notify_service.discord_service.send_dm.assert_awaited_once_with(111, "hello")
        real_notify_service.discord_service.send_dm_with_unwatch_button.assert_not_awaited()

    async def test_watcher_only_gets_unwatch_button_dm(self, real_notify_service):
        match = MockMatch()
        watcher = SimpleNamespace(user=SimpleNamespace(discord_id=222, dm_notifications=True))

        with self._patch_query('application.services.match_schedule_service.MatchPlayers.filter', []), \
             self._patch_query('application.services.match_schedule_service.Commentator.filter', []), \
             self._patch_query('application.services.match_schedule_service.Tracker.filter', []), \
             self._patch_query('application.services.match_schedule_service.MatchWatcher.filter', [watcher]):
            await real_notify_service.notify_match_participants(match, "hello")

        real_notify_service.discord_service.send_dm.assert_not_awaited()
        real_notify_service.discord_service.send_dm_with_unwatch_button.assert_awaited_once_with(222, "hello", match.id)

    async def test_player_who_is_also_watcher_gets_unwatch_button(self, real_notify_service):
        match = MockMatch()
        u = SimpleNamespace(discord_id=333, dm_notifications=True)
        player = SimpleNamespace(user=u)
        watcher = SimpleNamespace(user=u)

        with self._patch_query('application.services.match_schedule_service.MatchPlayers.filter', [player]), \
             self._patch_query('application.services.match_schedule_service.Commentator.filter', []), \
             self._patch_query('application.services.match_schedule_service.Tracker.filter', []), \
             self._patch_query('application.services.match_schedule_service.MatchWatcher.filter', [watcher]):
            await real_notify_service.notify_match_participants(match, "hello")

        real_notify_service.discord_service.send_dm.assert_not_awaited()
        real_notify_service.discord_service.send_dm_with_unwatch_button.assert_awaited_once_with(333, "hello", match.id)

    async def test_dm_notifications_opt_out_skips_user(self, real_notify_service):
        match = MockMatch()
        opted_out = SimpleNamespace(user=SimpleNamespace(discord_id=444, dm_notifications=False))

        with self._patch_query('application.services.match_schedule_service.MatchPlayers.filter', [opted_out]), \
             self._patch_query('application.services.match_schedule_service.Commentator.filter', []), \
             self._patch_query('application.services.match_schedule_service.Tracker.filter', []), \
             self._patch_query('application.services.match_schedule_service.MatchWatcher.filter', []):
            await real_notify_service.notify_match_participants(match, "hello")

        real_notify_service.discord_service.send_dm.assert_not_awaited()
        real_notify_service.discord_service.send_dm_with_unwatch_button.assert_not_awaited()

    async def test_each_recipient_gets_exactly_one_dm(self, real_notify_service):
        match = MockMatch()
        player_user = SimpleNamespace(discord_id=111, dm_notifications=True)
        crew_user = SimpleNamespace(discord_id=222, dm_notifications=True)
        watcher_user = SimpleNamespace(discord_id=333, dm_notifications=True)

        with self._patch_query('application.services.match_schedule_service.MatchPlayers.filter',
                               [SimpleNamespace(user=player_user)]), \
             self._patch_query('application.services.match_schedule_service.Commentator.filter',
                               [SimpleNamespace(user=crew_user)]), \
             self._patch_query('application.services.match_schedule_service.Tracker.filter', []), \
             self._patch_query('application.services.match_schedule_service.MatchWatcher.filter',
                               [SimpleNamespace(user=watcher_user)]):
            await real_notify_service.notify_match_participants(match, "msg")

        assert real_notify_service.discord_service.send_dm.await_count == 2
        assert real_notify_service.discord_service.send_dm_with_unwatch_button.await_count == 1
