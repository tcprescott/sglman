"""
Match Suggestion Service - Business Logic Layer

Suggests an optimal match start time by finding occupancy troughs across the
tournament room in the next 4 hours, falling back to the full event window when
no suitable slot exists in that range.

Capacity information is never surfaced to callers — the suggestion appears as a
neutral "best time," invisibly spreading load across the venue.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Sequence, Tuple

from application.repositories.player_availability_repository import PlayerAvailabilityRepository
from application.services.system_config_service import SystemConfigService
from application.tenant_context import require_tenant_id
from application.utils.timezone import now_eastern, parse_eastern_datetime, to_eastern
from models import Match, PlayerAvailability, Tournament, VolunteerAvailabilityStatus


_SLOT_INTERVAL_MIN = 30
_PRIMARY_WINDOW_HOURS = 4


class MatchSuggestionService:
    """Suggests match start times that minimise venue occupancy."""

    def __init__(self) -> None:
        self.availability_repository = PlayerAvailabilityRepository()

    async def suggest_match_time(
        self,
        tournament_id: int,
        player_ids: List[int],
    ) -> datetime:
        """Return a UTC datetime representing the best slot for the match.

        Primary search: next 4 hours within today's tournament-hours window.
        Fallback search: full remaining event window if primary yields no eligible slot.

        Raises ValueError if no eligible slot is found at all.
        """
        tournament = await Tournament.get_or_none(id=tournament_id, tenant_id=require_tenant_id())
        duration_min = (tournament.average_match_duration or 90) if tournament else 90
        duration = timedelta(minutes=duration_min)

        hours_map = await SystemConfigService.get_tournament_hours(tournament)
        event_start, event_end = await SystemConfigService.get_event_window(tournament)

        now = now_eastern()

        # Occupancy snapshot: all unfinished matches with a scheduled time
        existing_matches = await Match.filter(
            scheduled_at__isnull=False, confirmed_at__isnull=True,
            tenant_id=require_tenant_id(),
        ).prefetch_related('tournament', 'players')

        # Player availability windows for the entire event range
        event_start_dt = parse_eastern_datetime(event_start.isoformat(), '00:00')
        event_end_dt = parse_eastern_datetime(event_end.isoformat(), '23:59')
        avail_map = await self._build_availability_map(player_ids, event_start_dt, event_end_dt)
        has_windows = await self.availability_repository.has_any(player_ids)

        # --- Primary search: next 4 hours ---
        primary_end = now + timedelta(hours=_PRIMARY_WINDOW_HOURS)
        primary_candidates = self._generate_candidates(now, primary_end, hours_map, duration, event_start, event_end)
        result = self._best_candidate(primary_candidates, player_ids, avail_map, has_windows, existing_matches, duration)
        if result is not None:
            return result

        # --- Fallback search: full remaining event window ---
        fallback_candidates = self._generate_candidates(now, None, hours_map, duration, event_start, event_end)
        # Exclude slots already checked in the primary pass
        primary_set = {s for s, _ in primary_candidates}
        fallback_candidates = [(s, e) for s, e in fallback_candidates if s not in primary_set]
        result = self._best_candidate(fallback_candidates, player_ids, avail_map, has_windows, existing_matches, duration)
        if result is not None:
            return result

        raise ValueError("No available slot found for these players within the event schedule.")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _generate_candidates(
        self,
        from_dt: datetime,
        to_dt: Optional[datetime],
        hours_map,
        duration: timedelta,
        event_start,
        event_end,
    ) -> List[Tuple[datetime, datetime]]:
        """Generate (slot_start_eastern, slot_end_eastern) pairs at 30-min intervals."""
        from application.utils.timezone import EASTERN_TZ

        candidates: List[Tuple[datetime, datetime]] = []
        current_date = from_dt.date()
        end_date = to_dt.date() if to_dt else event_end

        while current_date <= end_date:
            if current_date < event_start or current_date > event_end:
                current_date += timedelta(days=1)
                continue

            window = hours_map.get(current_date)
            if window is None:
                if hours_map:
                    # Some days are configured — skip unconfigured days entirely
                    current_date += timedelta(days=1)
                    continue
                # No hours configured at all → treat every day as open all day
                from datetime import time as time_type
                open_t, close_t = time_type(0, 0), time_type(23, 30)
            else:
                open_t, close_t = window
            day_open = datetime(
                current_date.year, current_date.month, current_date.day,
                open_t.hour, open_t.minute, tzinfo=EASTERN_TZ,
            )
            day_close = datetime(
                current_date.year, current_date.month, current_date.day,
                close_t.hour, close_t.minute, tzinfo=EASTERN_TZ,
            )

            # Start no earlier than "from_dt" (rounded up to next slot)
            slot = max(day_open, from_dt)
            # Round up to next 30-min boundary
            slot = self._round_up_to_interval(slot)

            while slot + duration <= day_close:
                # Stay within the to_dt ceiling on the last day
                if to_dt and slot >= to_dt:
                    break
                candidates.append((slot, slot + duration))
                slot += timedelta(minutes=_SLOT_INTERVAL_MIN)

            current_date += timedelta(days=1)

        return candidates

    def _best_candidate(
        self,
        candidates: List[Tuple[datetime, datetime]],
        player_ids: List[int],
        avail_map,
        has_windows: set,
        existing_matches: List[Match],
        duration: timedelta,
    ) -> Optional[datetime]:
        """Score candidates and return the best UTC start time, or None."""
        scored: List[Tuple[int, int, datetime]] = []  # (occupancy, -preferred, slot_utc)

        for slot_start, slot_end in candidates:
            # Availability check
            preferred_count = 0
            eligible = True
            for pid in player_ids:
                windows: List[PlayerAvailability] = avail_map.get(pid, [])
                if pid not in has_windows:
                    # No windows declared → unconstrained
                    preferred_count += 0
                    continue
                status = _covers(windows, slot_start, slot_end)
                if status == VolunteerAvailabilityStatus.UNAVAILABLE:
                    eligible = False
                    break
                if status is None:
                    # Windows exist but none cover this slot → unavailable
                    eligible = False
                    break
                if status == VolunteerAvailabilityStatus.PREFERRED:
                    preferred_count += 1

            if not eligible:
                continue

            # Occupancy count
            occupancy = self._count_occupancy(existing_matches, slot_start, slot_end, duration)
            scored.append((occupancy, -preferred_count, slot_start))

        if not scored:
            return None

        scored.sort()
        best_eastern = scored[0][2]
        # Convert eastern-aware dt to UTC
        from datetime import timezone
        return best_eastern.astimezone(timezone.utc)

    @staticmethod
    def _count_occupancy(
        matches: List[Match],
        slot_start: datetime,
        slot_end: datetime,
        duration: timedelta,
    ) -> int:
        """Count distinct players in matches whose window overlaps [slot_start, slot_end)."""
        count = 0
        for m in matches:
            if not m.scheduled_at:
                continue
            m_start = to_eastern(m.scheduled_at)
            dur = duration
            if m.tournament and m.tournament.average_match_duration:
                dur = timedelta(minutes=m.tournament.average_match_duration)
            m_end = m_start + dur
            if m_start < slot_end and m_end > slot_start:
                count += len(list(m.players))
        return count

    @staticmethod
    def _round_up_to_interval(dt: datetime) -> datetime:
        """Round dt up to the nearest _SLOT_INTERVAL_MIN boundary."""
        minutes = dt.minute
        remainder = minutes % _SLOT_INTERVAL_MIN
        if remainder == 0 and dt.second == 0:
            return dt.replace(second=0, microsecond=0)
        add = _SLOT_INTERVAL_MIN - remainder
        return (dt + timedelta(minutes=add)).replace(second=0, microsecond=0)

    async def _build_availability_map(
        self, player_ids: List[int], start: datetime, end: datetime,
    ) -> dict[int, list]:
        rows = await self.availability_repository.for_users_overlapping(player_ids, start, end)
        out = {}
        for row in rows:
            out.setdefault(row.user_id, []).append(row)
        return out


def _covers(
    windows: Sequence[PlayerAvailability], start: datetime, end: datetime,
) -> Optional[VolunteerAvailabilityStatus]:
    result: Optional[VolunteerAvailabilityStatus] = None
    for w in windows:
        if w.starts_at < end and w.ends_at > start:
            if w.status == VolunteerAvailabilityStatus.UNAVAILABLE:
                return VolunteerAvailabilityStatus.UNAVAILABLE
            if w.status == VolunteerAvailabilityStatus.PREFERRED:
                result = VolunteerAvailabilityStatus.PREFERRED
            elif result is None:
                result = VolunteerAvailabilityStatus.AVAILABLE
    return result
