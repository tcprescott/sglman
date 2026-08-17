"""Coverage for MatchScheduleService seeding and the confirm/Challonge push.

The sibling ``test_match_schedule_service.py`` covers the seat/start/finish/
confirm lifecycle transitions and the DM message builders, and
``test_match_schedule_notifications.py`` covers the fan-out helpers — they moved
there when this file crossed the 800-line guideline. What is left drives the
untested scheduling/seeding branches against the real in-memory ORM: the roll
itself, the async task-queue handoff, the seed DMs it fire-and-forgets, and the
Challonge push that follows a confirm.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import (
    AuditLog,
    GeneratedSeeds,
    Match,
    MatchPlayers,
    Tournament,
)
from tests.factories import utc
from tests.services._match_schedule_setup import (
    build_service,
    make_dm_user,
    make_proctor,
    make_staff,
    record_winner,
)

UTC = timezone.utc


@pytest.fixture
def service():
    return build_service()


def _rolled(url: str, settings=None):
    """A ``ProviderCall`` stand-in for the seam ``generate_seed`` now goes through.

    ``MatchScheduleService`` calls ``generate_seed_call`` (not ``generate_seed``)
    so it can record the seed's provenance — the permalink *and* the settings as
    sent, plus what the roll cost.
    """
    from application.services.seedgen_service import RolledSeed
    from application.utils.seed_provider import ProviderCall

    return ProviderCall(
        value=RolledSeed(url=url, settings=settings),
        provider='alttpr', operation='generate_seed', attempts=1, latency_ms=5,
    )


def _submission(provider_task_id: str, branch: str = 'stable'):
    """What a task-queue backend returns instead of a seed: a handle to poll."""
    from application.services.seedgen_service import AsyncRollSubmission

    return AsyncRollSubmission(
        provider_task_id=provider_task_id,
        provider_params={'branch': branch},
        settings={'branch': branch, 'generate_spoilerlog': False},
    )



class TestGenerateSeed:
    async def test_success_creates_seed_writes_audit_and_returns_url(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T", seed_generator="alttpr")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30))
        await MatchPlayers.create(match=m, user=await make_dm_user(1, name="alice"))
        service.seedgen_service.generate_seed_call = AsyncMock(
            return_value=_rolled("https://alttpr.com/h/xyz", {"mode": "open"})
        )

        ok, message, url = await service.generate_seed(m.id, staff)

        assert ok is True
        assert url == "https://alttpr.com/h/xyz"
        assert "Seed generated successfully" in message
        assert await GeneratedSeeds.all().count() == 1
        refreshed = await Match.get(id=m.id)
        assert refreshed.generated_seed_id is not None
        assert await AuditLog.filter(action="match.seed_rolled").exists()

    async def test_seed_row_is_stamped_with_the_tenant(self, service, db, monkeypatch):
        """The service must stamp the tenant on the ``GeneratedSeeds`` row itself.

        The ``db`` fixture back-fills ``tenant_id`` on any scoped ``.create``
        that omits it, so an unstamped write is invisible to every other test
        here and only fails against Postgres (``null value in column
        "tenant_id"``). Assert on the kwargs the service actually passes.
        """
        staff = await make_staff()
        t = await Tournament.create(name="T", seed_generator="alttpr")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30))
        await MatchPlayers.create(match=m, user=await make_dm_user(3, name="alice"))
        service.seedgen_service.generate_seed_call = AsyncMock(
            return_value=_rolled("https://alttpr.com/h/xyz", {"mode": "open"})
        )

        passed = {}
        stamped_create = GeneratedSeeds.create

        async def spy(**kwargs):
            passed.update(kwargs)
            return await stamped_create(**kwargs)
        monkeypatch.setattr(GeneratedSeeds, 'create', spy)

        ok, _, _ = await service.generate_seed(m.id, staff)

        assert ok is True
        assert passed.get('tenant_id') == 1

    async def test_refuses_a_match_with_no_players(self, service, db):
        """One roll per match, and the seed reaches the players by DM.

        Rolling before they exist spends the single roll on nobody and leaves the
        real players unable to get another. The table hides the button, but REST
        and MCP reach this too, so the rule lives here.
        """
        staff = await make_staff()
        t = await Tournament.create(name="T", seed_generator="alttpr")
        m = await Match.create(tournament=t)
        service.seedgen_service.generate_seed_call = AsyncMock(return_value=_rolled("url"))

        ok, message, url = await service.generate_seed(m.id, staff)

        assert ok is False
        assert url is None
        assert "no players yet" in message
        service.seedgen_service.generate_seed_call.assert_not_awaited()
        assert await GeneratedSeeds.all().count() == 0

    async def test_returns_permission_error_for_non_privileged_actor(self, service, db):
        actor = await make_dm_user(2, name="nobody")
        t = await Tournament.create(name="T", seed_generator="alttpr")
        m = await Match.create(tournament=t)
        service.seedgen_service.generate_seed_call = AsyncMock(return_value=_rolled("url"))

        ok, message, url = await service.generate_seed(m.id, actor)

        assert ok is False
        assert url is None
        assert "do not have permission" in message
        service.seedgen_service.generate_seed_call.assert_not_awaited()

    async def test_returns_error_when_seed_already_exists(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T", seed_generator="alttpr")
        seed = await GeneratedSeeds.create(seed_url="https://existing")
        m = await Match.create(tournament=t, generated_seed=seed)
        service.seedgen_service.generate_seed_call = AsyncMock(return_value=_rolled("url"))

        ok, message, url = await service.generate_seed(m.id, staff)

        assert ok is False
        assert "already been generated" in message
        service.seedgen_service.generate_seed_call.assert_not_awaited()

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

    async def test_keyed_randomizer_blocked_when_credential_missing(self, service, db):
        # A keyed randomizer (dk64r) whose credential this community has not
        # supplied surfaces as a clean error tuple naming the missing key. The
        # real generator runs here (no AsyncMock) — the refusal comes from
        # credential resolution inside it, not from a boundary pre-check.
        staff = await make_staff(discord_id=9100)
        t = await Tournament.create(name="T", seed_generator="dk64r")
        m = await Match.create(tournament=t)
        # A player, because the roll is gated on having someone to DM the seed to
        # and this test is about what happens once generation is actually reached.
        await MatchPlayers.create(match=m, user=await make_dm_user(4, name="alice"))

        ok, message, url = await service.generate_seed(m.id, staff)

        assert ok is False
        assert url is None
        assert "DK64 Randomizer API key is not configured" in message

    async def test_keyed_randomizer_allowed_when_credential_configured(self, service, db):
        # dk64r is a task-queue backend, so a successful roll *starts* one rather
        # than returning a seed: no url yet, and a RUNNING ProviderTask holding
        # the upstream handle the worker will poll.
        from models import ProviderTask, ProviderTaskStatus, RandomizerCredential
        await RandomizerCredential.create(randomizer="dk64r", key="api_key", value="k")
        staff = await make_staff(discord_id=9200)
        t = await Tournament.create(name="T", seed_generator="dk64r")
        m = await Match.create(tournament=t)
        await MatchPlayers.create(match=m, user=await make_dm_user(21, name="p"))
        monkeypatch_submit = AsyncMock(return_value=_submission("up-42"))
        service.seedgen_service.submit_async_roll = monkeypatch_submit

        with patch(
            'application.services.seed_roll_service.SeedGenerationService',
            return_value=service.seedgen_service,
        ):
            ok, message, url = await service.generate_seed(m.id, staff)

        assert ok is True
        assert url is None
        assert "few minutes" in message
        task = await ProviderTask.get(match_id=m.id)
        assert task.status == ProviderTaskStatus.RUNNING
        assert task.provider_task_id == "up-42"
        assert task.requested_by_id == staff.id

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
        await MatchPlayers.create(match=m, user=await make_dm_user(5, name="alice"))
        service.seedgen_service.generate_seed_call = AsyncMock(side_effect=RuntimeError("boom"))

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
        monkeypatch.setattr("application.services.discord.discord_queue.enqueue", captured.append)
        await service.confirm_match(match, actor)
        for coro in captured:
            await coro

    async def test_pushes_result_when_confirmed(self, service, db, monkeypatch):
        staff = await make_staff()
        t = await Tournament.create(name="T")
        now = datetime.now(UTC)
        m = await Match.create(tournament=t, seated_at=now, started_at=now, finished_at=now)
        await MatchPlayers.create(match=m, user=await make_dm_user(1, name="w"), finish_rank=1)
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
        await MatchPlayers.create(match=m, user=await make_dm_user(2, name="w"), finish_rank=1)
        stub = MagicMock()
        stub.push_result_if_linked = AsyncMock(side_effect=RuntimeError("challonge down"))
        monkeypatch.setattr("application.services.challonge_service.ChallongeService", lambda: stub)

        # Must not raise despite the push blowing up.
        await self._run_and_drain(service, m, staff, monkeypatch)

        stub.push_result_if_linked.assert_awaited_once()
        refreshed = await Match.get(id=m.id)
        assert refreshed.confirmed_at is not None

class TestLifecycleTransitions:
    """End-to-end lifecycle against the real ORM (audit + event publish run for
    real), complementing the sibling suite's mock-based transition tests."""

    async def test_full_lifecycle_stamps_timestamps_and_audits(self, service, db):
        staff = await make_staff()
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30))
        player = await MatchPlayers.create(match=m, user=await make_dm_user(1, name="p"))

        await service.seat_match(m, staff)
        await service.start_match(m, staff)
        await service.finish_match(m, staff)
        await record_winner(player)
        await service.confirm_match(m, staff)

        refreshed = await Match.get(id=m.id)
        assert refreshed.seated_at is not None
        assert refreshed.started_at is not None
        assert refreshed.finished_at is not None
        assert refreshed.confirmed_at is not None
        for action in ("match.seated", "match.started", "match.finished", "match.confirmed"):
            assert await AuditLog.filter(action=action).exists()

    async def test_seat_rejects_a_match_with_no_players(self, service, db):
        """A bracket-scheduled match whose entrants are unresolved cannot check in."""
        staff = await make_staff()
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30))

        with pytest.raises(ValueError, match="no players"):
            await service.seat_match(m, staff)

        refreshed = await Match.get(id=m.id)
        assert refreshed.seated_at is None

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


class TestConfirmIsAdminOnly:
    """``confirm_match`` gates on ``can_confirm_match``, which excludes PROCTOR;
    every other lifecycle transition still gates on ``can_run_match``, which
    admits it. See docs/reference/authentication.md."""

    async def _live_match(self):
        t = await Tournament.create(name="T")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30))
        await MatchPlayers.create(match=m, user=await make_dm_user(1, name="p"))
        return m

    async def test_proctor_cannot_confirm(self, service, db):
        proctor = await make_proctor()
        m = await self._live_match()
        await service.seat_match(m, proctor)
        await service.start_match(m, proctor)
        await service.finish_match(m, proctor)
        # Recorded, so the refusal below is unambiguously about the role.
        await record_winner(await MatchPlayers.filter(match_id=m.id).first())

        with pytest.raises(PermissionError):
            await service.confirm_match(m, proctor)

        refreshed = await Match.get(id=m.id)
        assert refreshed.confirmed_at is None

    async def test_proctor_can_run_every_other_transition(self, service, db):
        proctor = await make_proctor()
        m = await self._live_match()

        await service.seat_match(m, proctor)
        await service.start_match(m, proctor)
        await service.finish_match(m, proctor)

        refreshed = await Match.get(id=m.id)
        assert refreshed.seated_at is not None
        assert refreshed.started_at is not None
        assert refreshed.finished_at is not None

    async def test_staff_can_still_confirm(self, service, db):
        staff = await make_staff()
        m = await self._live_match()
        await service.seat_match(m, staff)
        await service.start_match(m, staff)
        await service.finish_match(m, staff)
        await record_winner(await MatchPlayers.filter(match_id=m.id).first())

        await service.confirm_match(m, staff)

        refreshed = await Match.get(id=m.id)
        assert refreshed.confirmed_at is not None


class TestSeedDmDispatch:
    """Drive the ``_send_seed_dms`` coroutine that generate_seed fire-and-forgets."""

    async def test_sends_seed_dm_to_opted_in_players_and_logs_failures(self, service, db, monkeypatch):
        staff = await make_staff()
        t = await Tournament.create(name="T", seed_generator="alttpr")
        m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30))
        await MatchPlayers.create(match=m, user=await make_dm_user(1, name="alice"))
        await MatchPlayers.create(match=m, user=await make_dm_user(2, name="bob", dm=False))
        await MatchPlayers.create(match=m, user=await make_dm_user(3, name="carol"))
        service.seedgen_service.generate_seed_call = AsyncMock(
            return_value=_rolled("https://alttpr.com/h/xyz", {"mode": "open"})
        )
        # First recipient succeeds, second fails (exercises the warning branch).
        service.discord_service.send_dm = AsyncMock(side_effect=[(True, "ok"), (False, "blocked")])

        captured = []
        monkeypatch.setattr("application.services.discord.discord_queue.enqueue", captured.append)
        ok, _message, _url = await service.generate_seed(m.id, staff)
        assert ok is True
        for coro in captured:
            await coro

        # The opted-out player (id 2) is skipped; ids 1 and 3 each get one DM.
        sent_ids = sorted(call.args[0] for call in service.discord_service.send_dm.call_args_list)
        assert sent_ids == [1, 3]

