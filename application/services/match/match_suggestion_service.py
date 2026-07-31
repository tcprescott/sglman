"""
Match Suggestion Service - Business Logic Layer

Suggests an optimal match start time by finding occupancy troughs across the
tournament room in the next 4 hours, falling back to the full event window when
no suitable slot exists in that range.

Capacity information is never surfaced to callers — the suggestion appears as a
neutral "best time," invisibly spreading load across the venue.

A bracket matchup narrows that search to its round's window
(``Bracket.config['rounds'][str(round)]``): pass ``bracket_match_id`` and the
suggestion is a **hard bound** — only slots the match fits inside wholly are
offered, and "nothing fits" raises rather than silently drifting outside the
round. Either half of the window may stand alone (a start alone is a floor, an
end alone a deadline), so rounds configured before ``scheduled_end`` existed keep
working.
"""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from typing import List, Optional, Sequence, Tuple

from application.repositories.bracket_repository import BracketRepository
from application.repositories.player_availability_repository import PlayerAvailabilityRepository
from application.services.system_config_service import SystemConfigService
from application.services.timezone_service import TimezoneService
from application.tenant_context import require_tenant_id
from application.timezone_context import get_zone
from application.utils.timezone import now_local, parse_local_datetime, to_local
from models import Match, PlayerAvailability, Tournament, VolunteerAvailabilityStatus

_SLOT_INTERVAL_MIN = 30
_PRIMARY_WINDOW_HOURS = 4


class MatchSuggestionService:
    """Suggests match start times that minimise venue occupancy."""

    def __init__(self) -> None:
        self.availability_repository = PlayerAvailabilityRepository()
        self.bracket_repository = BracketRepository()

    async def suggest_match_time(
        self,
        tournament_id: int,
        player_ids: List[int],
        bracket_match_id: Optional[int] = None,
    ) -> datetime:
        """Return a UTC datetime representing the best slot for the match.

        Primary search: next 4 hours within today's tournament-hours window.
        Fallback search: full remaining event window if primary yields no eligible slot.

        ``bracket_match_id`` clamps both searches to the matchup's round window,
        as a hard bound: the match must fit inside it end to end.

        Raises ValueError if no eligible slot is found at all.
        """
        tournament = await Tournament.get_or_none(id=tournament_id, tenant_id=require_tenant_id())
        duration_min = (tournament.average_match_duration or 90) if tournament else 90
        duration = timedelta(minutes=duration_min)

        hours_map = await SystemConfigService.get_tournament_hours(tournament)
        event_start, event_end = await SystemConfigService.get_event_window(tournament)

        # The whole search is laid out on the community's clock, because the
        # operating hours and event window that bound it are written in that
        # clock. Only the returned instant is timezone-free.
        tz_name = await TimezoneService.tenant_timezone_name()
        tz = get_zone(tz_name)
        now = now_local(tz)

        round_start, round_end = await self._round_window(bracket_match_id, tz)
        in_round = round_start is not None or round_end is not None
        # A round that opens later moves the whole search forward; one that has
        # already opened leaves the "no earlier than now" floor alone.
        if round_start is not None:
            now = max(now, round_start)
        if round_end is not None and now + duration > round_end:
            raise ValueError(
                "This round's scheduled window has no room left for a match."
            )

        # Occupancy snapshot: all unfinished matches with a scheduled time
        existing_matches = await Match.filter(
            scheduled_at__isnull=False, confirmed_at__isnull=True,
            tenant_id=require_tenant_id(),
        ).prefetch_related('tournament', 'players')

        # Player availability windows for the entire event range
        event_start_dt = parse_local_datetime(event_start.isoformat(), '00:00', tz)
        event_end_dt = parse_local_datetime(event_end.isoformat(), '23:59', tz)
        avail_map = await self._build_availability_map(player_ids, event_start_dt, event_end_dt)
        has_windows = await self.availability_repository.has_any(player_ids)

        # --- Primary search: next 4 hours ---
        primary_end = now + timedelta(hours=_PRIMARY_WINDOW_HOURS)
        primary_candidates = self._generate_candidates(
            now, primary_end, hours_map, duration, event_start, event_end, tz, round_end,
        )
        result = self._best_candidate(primary_candidates, player_ids, avail_map, has_windows, existing_matches, duration)
        if result is not None:
            return result

        # --- Fallback search: full remaining event window ---
        fallback_candidates = self._generate_candidates(
            now, None, hours_map, duration, event_start, event_end, tz, round_end,
        )
        # Exclude slots already checked in the primary pass
        primary_set = {s for s, _ in primary_candidates}
        fallback_candidates = [(s, e) for s, e in fallback_candidates if s not in primary_set]
        result = self._best_candidate(fallback_candidates, player_ids, avail_map, has_windows, existing_matches, duration)
        if result is not None:
            return result

        if in_round:
            raise ValueError(
                "No available slot found for these players inside this round's "
                "scheduled window."
            )
        raise ValueError("No available slot found for these players within the event schedule.")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _round_window(
        self, bracket_match_id: Optional[int], tz,
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """The matchup's round window as ``(start, end)`` on ``tz``, or ``(None, None)``.

        Absent config — no bracket match, no ``rounds`` blob, no entry for this
        round, or a half left blank — is an absent bound, not an error: a round
        nobody has scheduled must not stop its matchups being scheduled.
        """
        if bracket_match_id is None:
            return None, None
        bracket_match = await self.bracket_repository.get_match_with_bracket(bracket_match_id)
        if bracket_match is None:
            return None, None
        rounds = (bracket_match.bracket.config or {}).get('rounds') or {}
        cfg = rounds.get(str(bracket_match.round)) or {}
        return (
            _parse_config_dt(cfg.get('scheduled_at'), tz),
            _parse_config_dt(cfg.get('scheduled_end'), tz),
        )

    def _generate_candidates(
        self,
        from_dt: datetime,
        to_dt: Optional[datetime],
        hours_map,
        duration: timedelta,
        event_start,
        event_end,
        tz,
        hard_end: Optional[datetime] = None,
    ) -> List[Tuple[datetime, datetime]]:
        """Generate (slot_start, slot_end) pairs at 30-min intervals, on ``tz``.

        ``tz`` is the community's zone, not the viewer's: the slots are bounded by
        the community's operating hours, so they must be laid out on the clock
        those hours are written in.

        ``hard_end`` is the round window's close, when the caller is scheduling a
        bracket matchup: a slot only survives if the whole match fits before it.
        """

        candidates: List[Tuple[datetime, datetime]] = []
        current_date = from_dt.date()
        end_date = to_dt.date() if to_dt else event_end
        if hard_end is not None:
            end_date = min(end_date, hard_end.date())

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
                open_t.hour, open_t.minute, tzinfo=tz,
            )
            day_close = datetime(
                current_date.year, current_date.month, current_date.day,
                close_t.hour, close_t.minute, tzinfo=tz,
            )

            # Start no earlier than "from_dt" (rounded up to next slot)
            slot = max(day_open, from_dt)
            # Round up to next 30-min boundary
            slot = self._round_up_to_interval(slot)

            while slot + duration <= day_close:
                # Stay within the to_dt ceiling on the last day
                if to_dt and slot >= to_dt:
                    break
                if hard_end is not None and slot + duration > hard_end:
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
        # Convert display-zone-aware dt to UTC
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
            m_start = to_local(m.scheduled_at)
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


def _parse_config_dt(value: Optional[str], tz) -> Optional[datetime]:
    """A stored UTC ISO string from the round blob → an aware datetime on ``tz``.

    The blob is schema-validated on the way in, so a bad string here means data
    that predates the validator; it degrades to "no bound" rather than breaking
    the suggestion.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    return parsed.astimezone(tz)


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
