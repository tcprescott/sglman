"""Tests for MatchSuggestionService (unit, no DB)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from application.services.match_suggestion_service import MatchSuggestionService

EASTERN_TZ = timezone(timedelta(hours=-5), 'EST')


def _eastern(hour, day=15, month=1):
    return datetime(2026, month, day, hour, 0, tzinfo=EASTERN_TZ)


def make_match(scheduled_hour=10, player_count=2, duration_min=90, tournament_duration=None):
    t = SimpleNamespace(
        average_match_duration=tournament_duration,
        name='Test',
    ) if tournament_duration is not None else SimpleNamespace(
        average_match_duration=None, name='Test',
    )
    return SimpleNamespace(
        scheduled_at=_eastern(scheduled_hour).astimezone(timezone.utc),
        players=[SimpleNamespace() for _ in range(player_count)],
        tournament=t,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    svc = object.__new__(MatchSuggestionService)
    svc.availability_repository = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# _round_up_to_interval (static)
# ---------------------------------------------------------------------------


class TestRoundUpToInterval:
    def test_already_on_boundary(self):
        dt = _eastern(10, 15)  # 10:00 -> on boundary
        result = MatchSuggestionService._round_up_to_interval(dt)
        assert result == dt.replace(second=0, microsecond=0)

    def test_rounds_up_to_next_30(self):
        dt = _eastern(10, 15).replace(minute=10)
        result = MatchSuggestionService._round_up_to_interval(dt)
        assert result.minute == 30

    def test_rounds_up_crossing_hour(self):
        dt = _eastern(10, 15).replace(minute=45)
        result = MatchSuggestionService._round_up_to_interval(dt)
        assert result.hour == 11
        assert result.minute == 0


# ---------------------------------------------------------------------------
# _count_occupancy (static)
# ---------------------------------------------------------------------------


class TestCountOccupancy:
    def test_counts_overlapping_match_players(self):
        slot_start = _eastern(10)
        slot_end = _eastern(12)
        match = make_match(scheduled_hour=10, player_count=2)
        count = MatchSuggestionService._count_occupancy(
            [match], slot_start, slot_end, timedelta(minutes=90),
        )
        assert count == 2

    def test_non_overlapping_match_not_counted(self):
        slot_start = _eastern(14)
        slot_end = _eastern(16)
        match = make_match(scheduled_hour=10, player_count=3)
        count = MatchSuggestionService._count_occupancy(
            [match], slot_start, slot_end, timedelta(minutes=90),
        )
        assert count == 0

    def test_no_matches_returns_zero(self):
        count = MatchSuggestionService._count_occupancy(
            [], _eastern(10), _eastern(12), timedelta(minutes=90),
        )
        assert count == 0

    def test_tournament_duration_used_for_match_end(self):
        # Tournament sets 30-min match duration; if it ends before slot, no count
        slot_start = _eastern(11)
        slot_end = _eastern(13)
        match = make_match(scheduled_hour=10, player_count=2, tournament_duration=30)
        count = MatchSuggestionService._count_occupancy(
            [match], slot_start, slot_end, timedelta(minutes=90),
        )
        assert count == 0


# ---------------------------------------------------------------------------
# _generate_candidates
# ---------------------------------------------------------------------------


class TestGenerateCandidates:
    def test_returns_candidates_within_event_window(self, service):
        from datetime import date
        event_start = date(2026, 1, 15)
        event_end = date(2026, 1, 15)
        from_dt = _eastern(10)  # 10:00 Eastern on Jan 15
        hours_map = {}
        candidates = service._generate_candidates(
            from_dt, None, hours_map, timedelta(hours=2),
            event_start, event_end,
        )
        # Without configured hours, every event day is open all day
        # from 10:00 we should have many 30-min slots throughout the rest of the day
        assert len(candidates) > 0

    def test_slots_at_30min_intervals(self, service):
        from datetime import date
        event_start = date(2026, 1, 15)
        event_end = date(2026, 1, 15)
        from datetime import time
        hours_map = {event_start: (time(10, 0), time(14, 0))}
        from_dt = _eastern(10)
        candidates = service._generate_candidates(
            from_dt, _eastern(14), hours_map, timedelta(hours=1),
            event_start, event_end,
        )
        if len(candidates) >= 2:
            gap = candidates[1][0] - candidates[0][0]
            assert gap == timedelta(minutes=30)

    def test_respects_event_date_bounds(self, service):
        from datetime import date
        event_start = date(2026, 2, 1)
        event_end = date(2026, 2, 1)
        from_dt = _eastern(10, day=1, month=2)
        candidates = service._generate_candidates(
            from_dt, None, {}, timedelta(hours=2),
            event_start, event_end,
        )
        # All candidates should start on the event date
        for slot_start, _ in candidates:
            assert slot_start.date() == event_start


# ---------------------------------------------------------------------------
# _best_candidate
# ---------------------------------------------------------------------------


class TestBestCandidate:
    def test_returns_none_when_no_candidates(self, service):
        result = service._best_candidate([], [], {}, set(), [], timedelta(hours=2))
        assert result is None

    def test_prefers_lower_occupancy(self, service):
        slot_busy = _eastern(10)
        slot_free = _eastern(12)
        duration = timedelta(hours=2)
        match = make_match(scheduled_hour=10, player_count=4)

        candidates = [
            (slot_busy, slot_busy + duration),
            (slot_free, slot_free + duration),
        ]
        result = service._best_candidate(candidates, [], {}, set(), [match], duration)
        # Should pick slot_free (lower occupancy)
        assert result is not None
        result_eastern_hour = result.astimezone(EASTERN_TZ).hour
        assert result_eastern_hour == 12

    def test_skips_unavailable_slots_for_players_with_windows(self, service):
        from models import VolunteerAvailabilityStatus

        slot_start = _eastern(10)
        slot_end = slot_start + timedelta(hours=2)
        player_id = 1

        unavailable_window = SimpleNamespace(
            starts_at=_eastern(8),
            ends_at=_eastern(14),
            status=VolunteerAvailabilityStatus.UNAVAILABLE,
        )
        avail_map = {player_id: [unavailable_window]}
        has_windows = {player_id}

        result = service._best_candidate(
            [(slot_start, slot_end)],
            [player_id],
            avail_map,
            has_windows,
            [],
            timedelta(hours=2),
        )
        assert result is None
