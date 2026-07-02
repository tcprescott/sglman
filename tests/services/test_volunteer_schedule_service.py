"""Tests for VolunteerScheduleService (unit, no DB)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.volunteer_schedule_service import VolunteerScheduleService

UTC = timezone.utc


def _dt(hour, day=4):
    return datetime(2026, 10, day, hour, 0, tzinfo=UTC)


def make_shift(**overrides):
    defaults = dict(
        id=1,
        position_id=1,
        position=SimpleNamespace(name='Check-in'),
        starts_at=_dt(8),
        ends_at=_dt(12),
        slots_needed=1,
        label='Shift 1',
        assignments=[],
        notes=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_assignment(**overrides):
    defaults = dict(id=1, shift_id=1, user_id=42, acknowledged_at=None)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def bypass_auth(monkeypatch):
    from application.services import auth_service

    async def allow(*_args, **_kwargs):
        return True

    async def noop_ensure(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth_service.AuthService, 'can_manage_volunteers', allow)
    monkeypatch.setattr(auth_service.AuthService, 'ensure', noop_ensure)


@pytest.fixture
def service():
    svc = object.__new__(VolunteerScheduleService)
    svc.shift_repository = MagicMock()
    svc.assignment_repository = MagicMock()
    svc.position_repository = MagicMock()
    svc.audit_service = MagicMock()
    svc.audit_service.write_log = AsyncMock()
    svc.discord_service = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# create_shift validation
# ---------------------------------------------------------------------------


class TestCreateShift:
    async def test_raises_when_end_before_start(self, service):
        with pytest.raises(ValueError, match='end after'):
            await service.create_shift(
                actor=MagicMock(), position_id=1,
                starts_at=_dt(12), ends_at=_dt(8),
            )

    async def test_raises_when_slots_less_than_one(self, service):
        with pytest.raises(ValueError, match='at least one'):
            await service.create_shift(
                actor=MagicMock(), position_id=1,
                starts_at=_dt(8), ends_at=_dt(12), slots_needed=0,
            )

    async def test_creates_shift_and_audits(self, service):
        shift = make_shift()
        service.shift_repository.create = AsyncMock(return_value=shift)
        result = await service.create_shift(
            actor=MagicMock(), position_id=1,
            starts_at=_dt(8), ends_at=_dt(12),
        )
        assert result is shift
        service.audit_service.write_log.assert_awaited_once()


# ---------------------------------------------------------------------------
# update_shift validation
# ---------------------------------------------------------------------------


class TestUpdateShift:
    async def test_raises_when_end_before_start(self, service):
        shift = make_shift()
        with pytest.raises(ValueError, match='end after'):
            await service.update_shift(
                actor=MagicMock(), shift=shift,
                starts_at=_dt(12), ends_at=_dt(8),
            )

    async def test_raises_when_slots_zero(self, service):
        shift = make_shift()
        with pytest.raises(ValueError, match='at least one'):
            await service.update_shift(
                actor=MagicMock(), shift=shift, slots_needed=0,
            )

    async def test_updates_and_audits(self, service):
        shift = make_shift()
        updated = make_shift(label='New Label')
        service.shift_repository.update = AsyncMock(return_value=updated)
        result = await service.update_shift(
            actor=MagicMock(), shift=shift, label='New Label',
        )
        assert result is updated
        service.audit_service.write_log.assert_awaited_once()


# ---------------------------------------------------------------------------
# delete_shift
# ---------------------------------------------------------------------------


class TestDeleteShift:
    async def test_deletes_and_audits(self, service):
        shift = make_shift(id=7)
        service.shift_repository.delete = AsyncMock()
        await service.delete_shift(actor=MagicMock(), shift=shift)
        service.shift_repository.delete.assert_awaited_once_with(shift)
        service.audit_service.write_log.assert_awaited_once()


# ---------------------------------------------------------------------------
# assign
# ---------------------------------------------------------------------------


class TestAssign:
    async def test_raises_when_already_on_shift(self, service):
        user = SimpleNamespace(id=42, preferred_name='Alice')
        shift = make_shift()
        service.assignment_repository.exists = AsyncMock(return_value=True)
        with pytest.raises(ValueError, match='already on this shift'):
            await service.assign(actor=MagicMock(), shift=shift, user=user)

    async def test_raises_when_overlapping(self, service):
        user = SimpleNamespace(id=42, preferred_name='Alice')
        shift = make_shift()
        service.assignment_repository.exists = AsyncMock(return_value=False)
        service.assignment_repository.overlapping_for_user = AsyncMock(return_value=[make_assignment()])
        with pytest.raises(ValueError, match='overlapping'):
            await service.assign(actor=MagicMock(), shift=shift, user=user)

    async def test_warns_when_overfilled(self, service):
        user = SimpleNamespace(id=42, preferred_name='Alice', discord_id=None, dm_notifications=True)
        shift = make_shift(slots_needed=1, assignments=['existing'])
        service.assignment_repository.exists = AsyncMock(return_value=False)
        service.assignment_repository.overlapping_for_user = AsyncMock(return_value=[])
        service.assignment_repository.create = AsyncMock(return_value=make_assignment())

        with patch.object(service, '_availability_warning', AsyncMock(return_value=None)):
            with patch(
                'application.services.volunteer_schedule_service.VolunteerAssignment',
            ) as MockAssn:
                MockAssn.filter.return_value.count = AsyncMock(return_value=2)
                _, warnings = await service.assign(actor=MagicMock(), shift=shift, user=user)
        assert any('slots filled' in w for w in warnings)

    async def test_creates_assignment_and_audits(self, service):
        user = SimpleNamespace(id=42, preferred_name='Alice', discord_id=None, dm_notifications=True)
        shift = make_shift()
        assignment = make_assignment()
        service.assignment_repository.exists = AsyncMock(return_value=False)
        service.assignment_repository.overlapping_for_user = AsyncMock(return_value=[])
        service.assignment_repository.create = AsyncMock(return_value=assignment)

        with patch.object(service, '_availability_warning', AsyncMock(return_value=None)):
            with patch(
                'application.services.volunteer_schedule_service.VolunteerAssignment',
            ) as MockAssn:
                MockAssn.filter.return_value.count = AsyncMock(return_value=0)
                result, warnings = await service.assign(actor=MagicMock(), shift=shift, user=user)

        assert result is assignment
        assert warnings == []
        service.audit_service.write_log.assert_awaited_once()


# ---------------------------------------------------------------------------
# acknowledge
# ---------------------------------------------------------------------------


class TestAcknowledge:
    async def test_raises_when_assignment_not_found(self, service):
        service.assignment_repository.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match='not found'):
            await service.acknowledge(assignment_id=999, user=SimpleNamespace(id=1))

    async def test_raises_when_not_owner(self, service):
        assignment = make_assignment(user_id=99)
        service.assignment_repository.get_by_id = AsyncMock(return_value=assignment)
        with pytest.raises(ValueError, match='your own'):
            await service.acknowledge(assignment_id=1, user=SimpleNamespace(id=42))

    async def test_sets_timestamp_and_audits(self, service):
        assignment = make_assignment(user_id=42, acknowledged_at=None)
        service.assignment_repository.get_by_id = AsyncMock(return_value=assignment)
        service.assignment_repository.save = AsyncMock()
        result = await service.acknowledge(assignment_id=1, user=SimpleNamespace(id=42))
        assert result.acknowledged_at is not None
        service.assignment_repository.save.assert_awaited_once()
        service.audit_service.write_log.assert_awaited_once()

    async def test_idempotent_when_already_acknowledged(self, service):
        ts = datetime.now(UTC)
        assignment = make_assignment(user_id=42, acknowledged_at=ts)
        service.assignment_repository.get_by_id = AsyncMock(return_value=assignment)
        service.assignment_repository.save = AsyncMock()
        result = await service.acknowledge(assignment_id=1, user=SimpleNamespace(id=42))
        assert result.acknowledged_at == ts
        service.assignment_repository.save.assert_not_awaited()


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------


class TestCoverage:
    async def test_reports_understaffed_shift(self, service):
        shift = make_shift(slots_needed=2, assignments=[SimpleNamespace()])
        shift.position = SimpleNamespace(name='Proctor')
        service.shift_repository.list_for_window = AsyncMock(return_value=[shift])
        rows = await service.coverage(_dt(0), _dt(23))
        assert len(rows) == 1
        assert rows[0]['filled'] == 1
        assert rows[0]['needed'] == 2
        assert rows[0]['understaffed'] is True

    async def test_reports_fully_staffed_shift(self, service):
        assignment = SimpleNamespace()
        shift = make_shift(slots_needed=1, assignments=[assignment])
        service.shift_repository.list_for_window = AsyncMock(return_value=[shift])
        rows = await service.coverage(_dt(0), _dt(23))
        assert rows[0]['understaffed'] is False
