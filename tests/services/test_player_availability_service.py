"""Tests for PlayerAvailabilityService (unit, no DB)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.services.player_availability_service import PlayerAvailabilityService
from models import VolunteerAvailabilityStatus

UTC = timezone.utc


def _dt(hour, minute=0):
    return datetime(2026, 10, 4, hour, minute, tzinfo=UTC)


def make_window(starts_hour, ends_hour, status=VolunteerAvailabilityStatus.AVAILABLE, note=None):
    return SimpleNamespace(
        starts_at=_dt(starts_hour),
        ends_at=_dt(ends_hour),
        status=status,
        note=note,
        user_id=1,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    svc = object.__new__(PlayerAvailabilityService)
    svc.repository = MagicMock()
    svc.audit_service = MagicMock()
    svc.audit_service.write_log = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# covers (static) — mirrors VolunteerAvailabilityService.covers
# ---------------------------------------------------------------------------


class TestCovers:
    def test_returns_none_when_no_windows(self):
        assert PlayerAvailabilityService.covers([], _dt(8), _dt(12)) is None

    def test_available_when_window_overlaps(self):
        windows = [make_window(7, 13)]
        result = PlayerAvailabilityService.covers(windows, _dt(8), _dt(12))
        assert result == VolunteerAvailabilityStatus.AVAILABLE

    def test_preferred_beats_available(self):
        windows = [
            make_window(7, 13, VolunteerAvailabilityStatus.AVAILABLE),
            make_window(8, 12, VolunteerAvailabilityStatus.PREFERRED),
        ]
        result = PlayerAvailabilityService.covers(windows, _dt(8), _dt(12))
        assert result == VolunteerAvailabilityStatus.PREFERRED

    def test_unavailable_wins_outright(self):
        windows = [
            make_window(7, 13, VolunteerAvailabilityStatus.PREFERRED),
            make_window(9, 11, VolunteerAvailabilityStatus.UNAVAILABLE),
        ]
        result = PlayerAvailabilityService.covers(windows, _dt(8), _dt(12))
        assert result == VolunteerAvailabilityStatus.UNAVAILABLE

    def test_non_overlapping_returns_none(self):
        windows = [make_window(14, 18)]
        result = PlayerAvailabilityService.covers(windows, _dt(8), _dt(12))
        assert result is None

    def test_touching_at_start_is_not_overlap(self):
        # ends_at == slot start, so no overlap
        windows = [make_window(4, 8)]
        result = PlayerAvailabilityService.covers(windows, _dt(8), _dt(12))
        assert result is None


# ---------------------------------------------------------------------------
# effective_segments (static)
# ---------------------------------------------------------------------------


class TestEffectiveSegments:
    def test_empty_when_range_is_zero(self):
        result = PlayerAvailabilityService.effective_segments([], _dt(8), _dt(8))
        assert result == []

    def test_single_full_range_available(self):
        windows = [make_window(8, 12)]
        segs = PlayerAvailabilityService.effective_segments(windows, _dt(8), _dt(12))
        assert len(segs) == 1
        assert segs[0][2] == VolunteerAvailabilityStatus.AVAILABLE

    def test_gap_produces_none_status(self):
        # Window only covers 10–12; 8–10 has no coverage
        windows = [make_window(10, 12)]
        segs = PlayerAvailabilityService.effective_segments(windows, _dt(8), _dt(12))
        statuses = [s[2] for s in segs]
        assert None in statuses
        assert VolunteerAvailabilityStatus.AVAILABLE in statuses

    def test_contiguous_same_status_merged(self):
        windows = [make_window(8, 10), make_window(10, 12)]
        segs = PlayerAvailabilityService.effective_segments(windows, _dt(8), _dt(12))
        assert len(segs) == 1

    def test_unavailable_creates_own_segment(self):
        windows = [
            make_window(8, 12, VolunteerAvailabilityStatus.AVAILABLE),
            make_window(10, 11, VolunteerAvailabilityStatus.UNAVAILABLE),
        ]
        segs = PlayerAvailabilityService.effective_segments(windows, _dt(8), _dt(12))
        statuses = [s[2] for s in segs]
        assert VolunteerAvailabilityStatus.UNAVAILABLE in statuses


# ---------------------------------------------------------------------------
# set_windows
# ---------------------------------------------------------------------------


class TestSetWindows:
    async def test_raises_when_window_ends_before_starts(self, service):
        user = SimpleNamespace(id=1)
        bad = (_dt(12), _dt(8), VolunteerAvailabilityStatus.AVAILABLE, None)
        with pytest.raises(ValueError, match='end after'):
            await service.set_windows(user, [bad])

    async def test_raises_when_window_ends_equal_to_starts(self, service):
        user = SimpleNamespace(id=1)
        bad = (_dt(8), _dt(8), VolunteerAvailabilityStatus.AVAILABLE, None)
        with pytest.raises(ValueError, match='end after'):
            await service.set_windows(user, [bad])


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


class TestClear:
    async def test_deletes_and_audits(self, service):
        service.repository.delete_for_user = AsyncMock()
        user = SimpleNamespace(id=1)
        await service.clear(user)
        service.repository.delete_for_user.assert_awaited_once_with(user)
        service.audit_service.write_log.assert_awaited_once()


# ---------------------------------------------------------------------------
# availability_map
# ---------------------------------------------------------------------------


class TestAvailabilityMap:
    async def test_groups_windows_by_user_id(self, service):
        w1 = SimpleNamespace(user_id=1)
        w2 = SimpleNamespace(user_id=2)
        w3 = SimpleNamespace(user_id=1)
        service.repository.for_users_overlapping = AsyncMock(return_value=[w1, w2, w3])
        result = await service.availability_map([1, 2], _dt(8), _dt(16))
        assert len(result[1]) == 2
        assert len(result[2]) == 1

    async def test_returns_empty_map_when_no_rows(self, service):
        service.repository.for_users_overlapping = AsyncMock(return_value=[])
        result = await service.availability_map([1], _dt(8), _dt(16))
        assert result == {}
