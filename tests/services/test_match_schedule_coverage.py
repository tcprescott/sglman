"""Coverage for MatchScheduleService seeding, confirm/Challonge push, and the
notification fan-out helpers (crew, acknowledgment, participants, subscribers).

The sibling ``test_match_schedule_service.py`` already covers the seat/start/
finish/confirm lifecycle transitions and the DM message builders; this file
drives the untested scheduling/seeding branches and each notifier's success,
opt-out, DM-failure, and exception paths against the real in-memory ORM.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.repositories import MatchAcknowledgmentRepository, MatchRepository
from application.services.audit_service import AuditService
from application.services.match_schedule_service import MatchScheduleService
from application.services.seedgen_service import SeedGenerationService
from models import (
    AuditLog,
    Commentator,
    GeneratedSeeds,
    Match,
    MatchAcknowledgment,
    MatchNotificationLevel,
    MatchPlayers,
    MatchWatcher,
    Role,
    StreamRoom,
    Tournament,
    TournamentNotificationPreference,
    Tracker,
    User,
    UserRole,
)

UTC = timezone.utc


def utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


async def make_user(discord_id, *, name="u", dm=True):
    return await User.create(
        discord_id=discord_id, username=name, display_name=name.upper(), dm_notifications=dm,
    )


async def make_staff(discord_id=9000):
    user = await make_user(discord_id, name="staff")
    await UserRole.create(user=user, role=Role.STAFF)
    return user


@pytest.fixture
def service():
    """A MatchScheduleService with real repositories/audit but a stubbed
    Discord service (so DM sends are recorded, never dispatched) and a real
    SeedGenerationService whose network call is monkeypatched per test."""
    svc = object.__new__(MatchScheduleService)
    svc.match_repository = MatchRepository()
    svc.acknowledgment_repository = MatchAcknowledgmentRepository()
    svc.seedgen_service = SeedGenerationService()
    svc.audit_service = AuditService()
    svc._seed_locks = {}
    discord = MagicMock()
    discord.send_dm = AsyncMock(return_value=(True, "ok"))
    discord.send_dm_with_unwatch_button = AsyncMock(return_value=(True, "ok"))
    discord.send_dm_with_acknowledgment_button = AsyncMock(return_value=(True, "ok"))
    discord.send_dm_with_crew_buttons = AsyncMock(return_value=(True, "ok"))
    svc.discord_service = discord
    return svc


class TestGenerateSeed:
    async def test_success_creates_seed_writes_audit_and_returns_url(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T", seed_generator="alttpr")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30))
        await MatchPlayers.create(match=m, user=await make_user(1, name="alice"))
        service.seedgen_service.generate_seed = AsyncMock(return_value="https://alttpr.com/h/xyz")

        ok, message, url = await service.generate_seed(m.id, staff)

        assert ok is True
        assert url == "https://alttpr.com/h/xyz"
        assert "Seed generated successfully" in message
        assert await GeneratedSeeds.all().count() == 1
        refreshed = await Match.get(id=m.id)
        assert refreshed.generated_seed_id is not None
        assert await AuditLog.filter(action="match.seed_rolled").exists()

    async def test_returns_permission_error_for_non_privileged_actor(self, service, db):
        actor = await make_user(2, name="nobody")
        t = await Tournament.create(name="T", seed_generator="alttpr")
        m = await Match.create(tournament=t)
        service.seedgen_service.generate_seed = AsyncMock(return_value="url")

        ok, message, url = await service.generate_seed(m.id, actor)

        assert ok is False
        assert url is None
        assert "do not have permission" in message
        service.seedgen_service.generate_seed.assert_not_awaited()

    async def test_returns_error_when_seed_already_exists(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T", seed_generator="alttpr")
        seed = await GeneratedSeeds.create(seed_url="https://existing")
        m = await Match.create(tournament=t, generated_seed=seed)
        service.seedgen_service.generate_seed = AsyncMock(return_value="url")

        ok, message, url = await service.generate_seed(m.id, staff)

        assert ok is False
        assert "already been generated" in message
        service.seedgen_service.generate_seed.assert_not_awaited()

    async def test_returns_error_when_no_generator_configured(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T", seed_generator=None)
        m = await Match.create(tournament=t)

        ok, message, url = await service.generate_seed(m.id, staff)

        assert ok is False
        assert "No seed generator configured" in message

    async def test_returns_error_when_generator_unsupported(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T", seed_generator="not-a-real-randomizer")
        m = await Match.create(tournament=t)

        ok, message, url = await service.generate_seed(m.id, staff)

        assert ok is False
        assert "not found" in message

    async def test_returns_in_progress_when_lock_held(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T", seed_generator="alttpr")
        m = await Match.create(tournament=t)
        lock = asyncio.Lock()
        await lock.acquire()
        service._seed_locks[m.id] = lock
        try:
            ok, message, url = await service.generate_seed(m.id, staff)
        finally:
            lock.release()

        assert ok is False
        assert "already in progress" in message

    async def test_returns_generic_error_when_generation_raises(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T", seed_generator="alttpr")
        m = await Match.create(tournament=t)
        service.seedgen_service.generate_seed = AsyncMock(side_effect=RuntimeError("boom"))

        ok, message, url = await service.generate_seed(m.id, staff)

        assert ok is False
        assert url is None
        assert "Seed generation failed" in message
        assert await GeneratedSeeds.all().count() == 0

    async def test_returns_generic_error_when_match_missing(self, service, db):
        staff = await make_staff()

        ok, message, url = await service.generate_seed(999999, staff)

        assert ok is False
        assert "Seed generation failed" in message


class TestConfirmMatchChallongePush:
    """confirm_match fire-and-forgets a Challonge result push after the base
    transition; drive the enqueued coroutine to exercise its body."""

    async def _run_and_drain(self, service, match, actor, monkeypatch):
        captured = []
        monkeypatch.setattr("application.services.discord_queue.enqueue", captured.append)
        await service.confirm_match(match, actor)
        for coro in captured:
            await coro

    async def test_pushes_result_when_confirmed(self, service, db, monkeypatch):
        staff = await make_staff()
        t = await Tournament.create(name="T")
        now = datetime.now(UTC)
        m = await Match.create(tournament=t, seated_at=now, started_at=now, finished_at=now)
        stub = MagicMock()
        stub.push_result_if_linked = AsyncMock(return_value=True)
        monkeypatch.setattr("application.services.challonge_service.ChallongeService", lambda: stub)

        await self._run_and_drain(service, m, staff, monkeypatch)

        stub.push_result_if_linked.assert_awaited_once()
        refreshed = await Match.get(id=m.id)
        assert refreshed.confirmed_at is not None

    async def test_swallows_challonge_push_failure(self, service, db, monkeypatch):
        staff = await make_staff()
        t = await Tournament.create(name="T")
        now = datetime.now(UTC)
        m = await Match.create(tournament=t, seated_at=now, started_at=now, finished_at=now)
        stub = MagicMock()
        stub.push_result_if_linked = AsyncMock(side_effect=RuntimeError("challonge down"))
        monkeypatch.setattr("application.services.challonge_service.ChallongeService", lambda: stub)

        # Must not raise despite the push blowing up.
        await self._run_and_drain(service, m, staff, monkeypatch)

        stub.push_result_if_linked.assert_awaited_once()
        refreshed = await Match.get(id=m.id)
        assert refreshed.confirmed_at is not None


class TestNotifyMatchCrew:
    async def test_approved_commentator_gets_plain_dm(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        await Commentator.create(match=m, user=await make_user(111, name="c"), approved=True)

        await service.notify_match_crew(m, "hello crew")

        service.discord_service.send_dm.assert_awaited_once_with(111, "hello crew")
        service.discord_service.send_dm_with_unwatch_button.assert_not_awaited()

    async def test_approved_tracker_gets_plain_dm(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        await Tracker.create(match=m, user=await make_user(112, name="tr"), approved=True)

        await service.notify_match_crew(m, "hi")

        service.discord_service.send_dm.assert_awaited_once_with(112, "hi")

    async def test_watcher_gets_unwatch_button_dm(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        await MatchWatcher.create(match=m, user=await make_user(222, name="w"))

        await service.notify_match_crew(m, "watch msg")

        service.discord_service.send_dm.assert_not_awaited()
        service.discord_service.send_dm_with_unwatch_button.assert_awaited_once_with(222, "watch msg", m.id)

    async def test_player_who_is_crew_is_excluded(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        u = await make_user(333, name="pc")
        await MatchPlayers.create(match=m, user=u)
        await Commentator.create(match=m, user=u, approved=True)

        await service.notify_match_crew(m, "hi")

        service.discord_service.send_dm.assert_not_awaited()
        service.discord_service.send_dm_with_unwatch_button.assert_not_awaited()

    async def test_unapproved_crew_skipped(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        await Commentator.create(match=m, user=await make_user(444, name="pending"), approved=False)

        await service.notify_match_crew(m, "hi")

        service.discord_service.send_dm.assert_not_awaited()

    async def test_opted_out_crew_skipped(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        await Commentator.create(match=m, user=await make_user(555, name="mute", dm=False), approved=True)

        await service.notify_match_crew(m, "hi")

        service.discord_service.send_dm.assert_not_awaited()

    async def test_dm_failure_is_swallowed(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        await Commentator.create(match=m, user=await make_user(666, name="c"), approved=True)
        service.discord_service.send_dm = AsyncMock(return_value=(False, "blocked"))

        # A failed DM is logged, not raised.
        await service.notify_match_crew(m, "hi")

        service.discord_service.send_dm.assert_awaited_once()

    async def test_unexpected_exception_is_swallowed(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        await Commentator.create(match=m, user=await make_user(777, name="c"), approved=True)
        service.discord_service.send_dm = AsyncMock(side_effect=RuntimeError("kaboom"))

        # Outer try/except must swallow the send error.
        await service.notify_match_crew(m, "hi")


class TestNotifyAcknowledgmentRequest:
    async def _setup_match(self, *, stream_room=True):
        t = await Tournament.create(name="T")
        sr = await StreamRoom.create(name="Stage 1") if stream_room else None
        return await Match.create(tournament=t, stream_room=sr, scheduled_at=utc(2025, 1, 15, 19, 30))

    async def test_sends_ack_button_to_pending_player(self, service, db):
        m = await self._setup_match()
        player = await make_user(111, name="alice")
        await MatchPlayers.create(match=m, user=player)
        await MatchAcknowledgment.create(match=m, user=player, acknowledged_at=None)

        await service.notify_acknowledgment_request(m, rescheduled=False)

        call = service.discord_service.send_dm_with_acknowledgment_button.call_args
        assert call.args[0] == 111
        assert call.args[2] == m.id

    async def test_rescheduled_flag_still_sends(self, service, db):
        m = await self._setup_match(stream_room=False)
        player = await make_user(112, name="bob")
        await MatchPlayers.create(match=m, user=player)
        await MatchAcknowledgment.create(match=m, user=player, acknowledged_at=None)

        await service.notify_acknowledgment_request(m, rescheduled=True)

        service.discord_service.send_dm_with_acknowledgment_button.assert_awaited_once()

    async def test_already_acknowledged_is_skipped(self, service, db):
        m = await self._setup_match()
        player = await make_user(113, name="carol")
        await MatchPlayers.create(match=m, user=player)
        await MatchAcknowledgment.create(match=m, user=player, acknowledged_at=utc(2025, 1, 15, 20, 0))

        await service.notify_acknowledgment_request(m, rescheduled=False)

        service.discord_service.send_dm_with_acknowledgment_button.assert_not_awaited()

    async def test_opted_out_player_is_skipped(self, service, db):
        m = await self._setup_match()
        player = await make_user(114, name="dave", dm=False)
        await MatchPlayers.create(match=m, user=player)
        await MatchAcknowledgment.create(match=m, user=player, acknowledged_at=None)

        await service.notify_acknowledgment_request(m, rescheduled=False)

        service.discord_service.send_dm_with_acknowledgment_button.assert_not_awaited()

    async def test_dm_failure_is_swallowed(self, service, db):
        m = await self._setup_match()
        player = await make_user(115, name="erin")
        await MatchPlayers.create(match=m, user=player)
        await MatchAcknowledgment.create(match=m, user=player, acknowledged_at=None)
        service.discord_service.send_dm_with_acknowledgment_button = AsyncMock(return_value=(False, "blocked"))

        await service.notify_acknowledgment_request(m, rescheduled=False)

        service.discord_service.send_dm_with_acknowledgment_button.assert_awaited_once()

    async def test_unexpected_exception_is_swallowed(self, service, db):
        m = await self._setup_match()
        player = await make_user(116, name="fred")
        await MatchPlayers.create(match=m, user=player)
        await MatchAcknowledgment.create(match=m, user=player, acknowledged_at=None)
        service.discord_service.send_dm_with_acknowledgment_button = AsyncMock(side_effect=RuntimeError("x"))

        await service.notify_acknowledgment_request(m, rescheduled=False)


class TestNotifyMatchParticipantsBranches:
    """Branches the sibling suite leaves uncovered: the approved-tracker path
    and the DM-failure / unexpected-exception handling."""

    async def test_approved_tracker_receives_dm(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        await Tracker.create(match=m, user=await make_user(444, name="tr"), approved=True)

        await service.notify_match_participants(m, "hi")

        service.discord_service.send_dm.assert_awaited_once_with(444, "hi")

    async def test_dm_failure_is_swallowed(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        await MatchPlayers.create(match=m, user=await make_user(445, name="p"))
        service.discord_service.send_dm = AsyncMock(return_value=(False, "blocked"))

        await service.notify_match_participants(m, "hi")

        service.discord_service.send_dm.assert_awaited_once()

    async def test_unexpected_exception_is_swallowed(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        await MatchPlayers.create(match=m, user=await make_user(446, name="p"))
        service.discord_service.send_dm = AsyncMock(side_effect=RuntimeError("kaboom"))

        await service.notify_match_participants(m, "hi")


class TestNotifySubscriberFailurePaths:
    async def test_tournament_subscriber_dm_failure_is_swallowed(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        sub = await make_user(555, name="sub")
        await TournamentNotificationPreference.create(
            user=sub, tournament=t, match_notifications=MatchNotificationLevel.ALL,
        )
        service.discord_service.send_dm_with_crew_buttons = AsyncMock(return_value=(False, "blocked"))

        await service.notify_tournament_subscribers_scheduled(m, "msg", [])

        service.discord_service.send_dm_with_crew_buttons.assert_awaited_once_with(555, "msg", m.id)

    async def test_stream_candidate_subscriber_dm_failure_is_swallowed(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30))
        sub = await make_user(556, name="sub")
        await TournamentNotificationPreference.create(
            user=sub, tournament=t, match_notifications=MatchNotificationLevel.STREAMED_AND_CANDIDATES,
        )
        service.discord_service.send_dm_with_crew_buttons = AsyncMock(return_value=(False, "blocked"))

        await service.notify_stream_candidate_subscribers(m, [])

        call = service.discord_service.send_dm_with_crew_buttons.call_args
        assert call.args[0] == 556


class TestLifecycleTransitions:
    """End-to-end lifecycle against the real ORM (audit + event publish run for
    real), complementing the sibling suite's mock-based transition tests."""

    async def test_full_lifecycle_stamps_timestamps_and_audits(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30))
        await MatchPlayers.create(match=m, user=await make_user(1, name="p"))

        await service.seat_match(m, staff)
        await service.start_match(m, staff)
        await service.finish_match(m, staff)
        await service.confirm_match(m, staff)

        refreshed = await Match.get(id=m.id)
        assert refreshed.seated_at is not None
        assert refreshed.started_at is not None
        assert refreshed.finished_at is not None
        assert refreshed.confirmed_at is not None
        for action in ("match.seated", "match.started", "match.finished", "match.confirmed"):
            assert await AuditLog.filter(action=action).exists()

    async def test_seat_twice_raises(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, seated_at=datetime.now(UTC))
        with pytest.raises(ValueError, match="already checked in"):
            await service.seat_match(m, staff)

    async def test_start_before_seat_raises(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        with pytest.raises(ValueError, match="checked in before starting"):
            await service.start_match(m, staff)

    async def test_start_twice_raises(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T")
        now = datetime.now(UTC)
        m = await Match.create(tournament=t, seated_at=now, started_at=now)
        with pytest.raises(ValueError, match="already started"):
            await service.start_match(m, staff)

    async def test_finish_before_start_raises(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, seated_at=datetime.now(UTC))
        with pytest.raises(ValueError, match="started before finishing"):
            await service.finish_match(m, staff)

    async def test_finish_twice_raises(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T")
        now = datetime.now(UTC)
        m = await Match.create(tournament=t, seated_at=now, started_at=now, finished_at=now)
        with pytest.raises(ValueError, match="already finished"):
            await service.finish_match(m, staff)

    async def test_confirm_before_finish_raises(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        with pytest.raises(ValueError, match="finished before confirming"):
            await service.confirm_match(m, staff)

    async def test_confirm_twice_raises(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T")
        now = datetime.now(UTC)
        m = await Match.create(
            tournament=t, seated_at=now, started_at=now, finished_at=now, confirmed_at=now,
        )
        with pytest.raises(ValueError, match="already confirmed"):
            await service.confirm_match(m, staff)


class TestSeedDmDispatch:
    """Drive the ``_send_seed_dms`` coroutine that generate_seed fire-and-forgets."""

    async def test_sends_seed_dm_to_opted_in_players_and_logs_failures(self, service, db, monkeypatch):
        staff = await make_staff()
        t = await Tournament.create(name="T", seed_generator="alttpr")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30))
        await MatchPlayers.create(match=m, user=await make_user(1, name="alice"))
        await MatchPlayers.create(match=m, user=await make_user(2, name="bob", dm=False))
        await MatchPlayers.create(match=m, user=await make_user(3, name="carol"))
        service.seedgen_service.generate_seed = AsyncMock(return_value="https://alttpr.com/h/xyz")
        # First recipient succeeds, second fails (exercises the warning branch).
        service.discord_service.send_dm = AsyncMock(side_effect=[(True, "ok"), (False, "blocked")])

        captured = []
        monkeypatch.setattr("application.services.discord_queue.enqueue", captured.append)
        ok, _message, _url = await service.generate_seed(m.id, staff)
        assert ok is True
        for coro in captured:
            await coro

        # The opted-out player (id 2) is skipped; ids 1 and 3 each get one DM.
        sent_ids = sorted(call.args[0] for call in service.discord_service.send_dm.call_args_list)
        assert sent_ids == [1, 3]


class TestNotifyMatchParticipantsCommentatorAndWatcher:
    async def test_approved_commentator_receives_dm(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        await Commentator.create(match=m, user=await make_user(211, name="c"), approved=True)

        await service.notify_match_participants(m, "hi")

        service.discord_service.send_dm.assert_awaited_once_with(211, "hi")

    async def test_watcher_receives_unwatch_button(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        await MatchWatcher.create(match=m, user=await make_user(212, name="w"))

        await service.notify_match_participants(m, "hi")

        service.discord_service.send_dm.assert_not_awaited()
        service.discord_service.send_dm_with_unwatch_button.assert_awaited_once_with(212, "hi", m.id)


class TestNotifyStreamCandidateSubscribersExtra:
    async def test_returns_early_when_match_has_stream_room(self, service, db):
        t = await Tournament.create(name="T")
        sr = await StreamRoom.create(name="Stage 1")
        m = await Match.create(tournament=t, stream_room=sr)
        sub = await make_user(700, name="sub")
        await TournamentNotificationPreference.create(
            user=sub, tournament=t, match_notifications=MatchNotificationLevel.STREAMED_AND_CANDIDATES,
        )

        await service.notify_stream_candidate_subscribers(m, [])

        service.discord_service.send_dm_with_crew_buttons.assert_not_awaited()

    async def test_send_raising_is_swallowed(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30))
        sub = await make_user(701, name="sub")
        await TournamentNotificationPreference.create(
            user=sub, tournament=t, match_notifications=MatchNotificationLevel.STREAMED_AND_CANDIDATES,
        )
        service.discord_service.send_dm_with_crew_buttons = AsyncMock(side_effect=RuntimeError("boom"))

        await service.notify_stream_candidate_subscribers(m, [])


class TestNotifyTournamentSubscribersScheduledExtra:
    async def test_send_raising_is_swallowed(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        sub = await make_user(710, name="sub")
        await TournamentNotificationPreference.create(
            user=sub, tournament=t, match_notifications=MatchNotificationLevel.ALL,
        )
        service.discord_service.send_dm_with_crew_buttons = AsyncMock(side_effect=RuntimeError("boom"))

        await service.notify_tournament_subscribers_scheduled(m, "msg", [])


class TestNotifyMatchScheduledFanOut:
    async def test_enqueues_ack_crew_and_subscribers(self, service, db):
        t = await Tournament.create(name="T")
        sr = await StreamRoom.create(name="Stage 1")
        m = await Match.create(tournament=t, stream_room=sr, scheduled_at=utc(2025, 1, 15, 19, 30))
        await MatchPlayers.create(match=m, user=await make_user(811, name="p"))

        captured = []
        import application.services.discord_queue as dq
        original = dq.enqueue
        dq.enqueue = captured.append
        try:
            await service.notify_match_scheduled(m, rescheduled=False, is_stream_candidate=False)
        finally:
            dq.enqueue = original
        # Assert the specific notifiers were fanned out (not just the count), so a
        # regression that enqueues the wrong notifier with the same arity is caught.
        enqueued = {c.cr_code.co_qualname for c in captured}
        for coro in captured:
            coro.close()
        assert enqueued == {
            "MatchScheduleService.notify_acknowledgment_request",
            "MatchScheduleService.notify_match_crew",
            "MatchScheduleService.notify_tournament_subscribers_scheduled",
        }

    async def test_stream_candidate_adds_fourth_enqueue(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30))
        await MatchPlayers.create(match=m, user=await make_user(812, name="p"))

        captured = []
        import application.services.discord_queue as dq
        original = dq.enqueue
        dq.enqueue = captured.append
        try:
            await service.notify_match_scheduled(m, rescheduled=True, is_stream_candidate=True)
        finally:
            dq.enqueue = original
        enqueued = {c.cr_code.co_qualname for c in captured}
        for coro in captured:
            coro.close()
        # The stream-candidate branch adds the subscriber fan-out as the 4th enqueue.
        assert enqueued == {
            "MatchScheduleService.notify_acknowledgment_request",
            "MatchScheduleService.notify_match_crew",
            "MatchScheduleService.notify_tournament_subscribers_scheduled",
            "MatchScheduleService.notify_stream_candidate_subscribers",
        }

    async def test_notify_stream_candidate_enqueues_subscriber_fanout(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30))
        await MatchPlayers.create(match=m, user=await make_user(813, name="p"))

        captured = []
        import application.services.discord_queue as dq
        original = dq.enqueue
        dq.enqueue = captured.append
        try:
            await service.notify_stream_candidate(m)
        finally:
            dq.enqueue = original
        for coro in captured:
            coro.close()
        assert len(captured) == 1


class TestCollectNotifiedDiscordIds:
    async def test_appends_unique_tracker_id(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        await MatchPlayers.create(match=m, user=await make_user(111, name="p"))
        await Commentator.create(match=m, user=await make_user(222, name="c"), approved=True)
        await Tracker.create(match=m, user=await make_user(333, name="tr"), approved=True)

        ids = await service._collect_notified_discord_ids(m)

        assert ids == [111, 222, 333]

    async def test_unapproved_tracker_excluded(self, service, db):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t)
        await MatchPlayers.create(match=m, user=await make_user(111, name="p"))
        await Tracker.create(match=m, user=await make_user(999, name="tr"), approved=False)

        ids = await service._collect_notified_discord_ids(m)

        assert ids == [111]
