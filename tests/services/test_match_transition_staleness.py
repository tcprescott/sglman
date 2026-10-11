"""Lifecycle transitions acting on a match loaded before someone else moved it.

Every board handler loads the match when its dialog opens and hands that object
to the service when the proctor taps the button. On a show floor that object is
routinely stale: a second proctor checks the same players in, a stream manager
assigns a stage, or one phone double-taps. The transition must decide from the
row as it stands, and must write only the timestamp it owns.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from models import AuditLog, Match, MatchPlayers, Stage, Tournament
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


async def _match(**fields) -> Match:
    t = await Tournament.create(name="T")
    m = await Match.create(tournament=t, scheduled_at=utc(2025, 1, 15, 19, 30), **fields)
    await MatchPlayers.create(match=m, user=await make_dm_user(1, name="p"))
    return m


class TestStaleSnapshot:
    async def test_stale_check_in_does_not_rewind_a_started_match(self, service, db):
        proctor = await make_proctor()
        m = await _match()
        stale = await Match.get(id=m.id)

        fresh = await Match.get(id=m.id)
        await service.seat_match(fresh, proctor)
        await service.start_match(fresh, proctor)

        with pytest.raises(ValueError, match="already checked in"):
            await service.seat_match(stale, proctor)

        row = await Match.get(id=m.id)
        assert row.started_at is not None

    async def test_transition_keeps_a_stage_assigned_after_the_load(self, service, db):
        proctor = await make_proctor()
        m = await _match()
        stale = await Match.get(id=m.id)

        stage = await Stage.create(name="Main")
        await Match.filter(id=m.id).update(stage_id=stage.id)

        await service.seat_match(stale, proctor)

        row = await Match.get(id=m.id)
        assert row.stage_id == stage.id
        assert row.seated_at is not None

    async def test_stale_confirm_is_refused_once_confirmed(self, service, db):
        staff = await make_staff()
        now = datetime.now(UTC)
        m = await _match(seated_at=now, started_at=now, finished_at=now)
        await record_winner(await MatchPlayers.filter(match_id=m.id).first())
        first = await Match.get(id=m.id)
        second = await Match.get(id=m.id)

        await service.confirm_match(first, staff)
        with pytest.raises(ValueError, match="already confirmed"):
            await service.confirm_match(second, staff)

        assert await AuditLog.filter(action="match.confirmed").count() == 1


class TestDoubleTap:
    async def test_concurrent_starts_stamp_and_audit_once(self, service, db):
        proctor = await make_proctor()
        m = await _match(seated_at=datetime.now(UTC))
        a = await Match.get(id=m.id)
        b = await Match.get(id=m.id)

        results = await asyncio.gather(
            service.start_match(a, proctor),
            service.start_match(b, proctor),
            return_exceptions=True,
        )

        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 1
        assert isinstance(errors[0], ValueError)
        assert await AuditLog.filter(action="match.started").count() == 1
