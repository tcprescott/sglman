"""Tests for VolunteerAutoscheduleService (unit, no DB)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.services.volunteer_autoschedule_service import VolunteerAutoscheduleService

UTC = timezone.utc


def _dt(hour, day=4):
    return datetime(2026, 10, day, hour, 0, tzinfo=UTC)


def make_shift(shift_id, starts, ends, position_id=1, slots_needed=1, assignments=None):
    return SimpleNamespace(
        id=shift_id,
        position_id=position_id,
        position=SimpleNamespace(name='Check-in'),
        starts_at=starts,
        ends_at=ends,
        slots_needed=slots_needed,
        assignments=assignments or [],
    )


def make_user(uid, name='Alice'):
    return SimpleNamespace(id=uid, preferred_name=name)


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
    svc = object.__new__(VolunteerAutoscheduleService)
    svc.shift_repository = MagicMock()
    svc.assignment_repository = MagicMock()
    svc.profile_service = MagicMock()
    svc.availability_service = MagicMock()
    svc.schedule_service = MagicMock()
    svc.audit_service = MagicMock()
    svc.audit_service.write_log = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# _overlaps (static)
# ---------------------------------------------------------------------------


class TestOverlaps:
    def test_overlapping(self):
        existing = [(_dt(8), _dt(12))]
        assert VolunteerAutoscheduleService._overlaps(existing, _dt(10), _dt(14)) is True

    def test_non_overlapping(self):
        existing = [(_dt(8), _dt(12))]
        assert VolunteerAutoscheduleService._overlaps(existing, _dt(12), _dt(16)) is False

    def test_empty_existing(self):
        assert VolunteerAutoscheduleService._overlaps([], _dt(8), _dt(12)) is False

    def test_adjacent_not_overlapping(self):
        existing = [(_dt(8), _dt(12))]
        assert VolunteerAutoscheduleService._overlaps(existing, _dt(12), _dt(16)) is False


# ---------------------------------------------------------------------------
# _hours (static)
# ---------------------------------------------------------------------------


class TestHours:
    def test_four_hour_shift(self):
        assert VolunteerAutoscheduleService._hours(_dt(8), _dt(12)) == 4.0

    def test_zero_when_same_time(self):
        assert VolunteerAutoscheduleService._hours(_dt(8), _dt(8)) == 0.0

    def test_fractional_hours(self):
        start = _dt(8)
        end = start + timedelta(minutes=90)
        assert VolunteerAutoscheduleService._hours(start, end) == 1.5


# ---------------------------------------------------------------------------
# _unfilled_summary (static)
# ---------------------------------------------------------------------------


class TestUnfilledSummary:
    def test_all_filled_returns_empty(self):
        shift = make_shift(1, _dt(8), _dt(12), slots_needed=1, assignments=[SimpleNamespace()])
        result = VolunteerAutoscheduleService._unfilled_summary([shift], {1: 1})
        assert result == []

    def test_unfilled_shift_in_result(self):
        shift = make_shift(1, _dt(8), _dt(12), slots_needed=2, assignments=[])
        result = VolunteerAutoscheduleService._unfilled_summary([shift], {1: 0})
        assert len(result) == 1
        assert result[0]['open'] == 2


# ---------------------------------------------------------------------------
# _pick (unit)
# ---------------------------------------------------------------------------


class TestPick:
    def test_returns_none_when_pool_empty(self, service):
        shift = make_shift(1, _dt(8), _dt(12))
        result = service._pick(shift, [], [], {}, {}, {}, {}, {})
        assert result is None

    def test_skips_user_already_on_shift(self, service):
        user = make_user(1)
        shift = make_shift(1, _dt(8), _dt(12))
        on_shift = {1: {1}}
        result = service._pick(shift, [user], [1], {}, {}, {1: []}, {1: 0.0}, on_shift)
        assert result is None

    def test_skips_user_with_wrong_qualification(self, service):
        user = make_user(1)
        shift = make_shift(1, _dt(8), _dt(12), position_id=5)
        quals = {1: {99}}  # qualified for position 99, not 5
        on_shift = {1: set()}
        result = service._pick(shift, [user], [1], quals, {}, {1: []}, {1: 0.0}, on_shift)
        assert result is None

    def test_picks_available_user(self, service):
        user = make_user(1)
        shift = make_shift(1, _dt(8), _dt(12))
        on_shift = {1: set()}
        result = service._pick(shift, [user], [1], {}, {}, {1: []}, {1: 0.0}, on_shift)
        assert result is user

    def test_prefers_lower_hours_user(self, service):
        alice = make_user(1, 'Alice')
        bob = make_user(2, 'Bob')
        shift = make_shift(1, _dt(8), _dt(12))
        on_shift = {1: set(), 2: set()}
        hours = {1: 8.0, 2: 0.0}
        result = service._pick(
            shift, [alice, bob], [1, 2], {}, {},
            {1: [], 2: []}, hours, on_shift,
        )
        assert result is bob  # Bob has fewer hours


# ---------------------------------------------------------------------------
# clear_draft
# ---------------------------------------------------------------------------


class TestClearDraft:
    async def test_removes_auto_assignments_and_audits(self, service):
        service.assignment_repository.delete_auto_for_window = AsyncMock(return_value=3)
        removed = await service.clear_draft(actor=MagicMock(), start=_dt(0), end=_dt(23))
        assert removed == 3
        service.audit_service.write_log.assert_awaited_once()
