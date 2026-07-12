"""
Reports Service - Business Logic Layer

One method per report. All time math runs in US/Eastern; inputs and outputs
are timezone-aware datetimes.
"""

from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from application.services.system_config_service import SystemConfigService
from application.tenant_context import require_tenant_id
from application.utils.timezone import EASTERN_TZ, to_eastern
from models import (
    Match,
    StreamRoom,
    User,
)


DEFAULT_MATCH_DURATION_MIN = 90
ON_TIME_THRESHOLD_MIN = 5


class ReportsService:
    """Generates aggregated views over matches, crew, stages, and audit logs."""

    # --- Capacity Forecast -------------------------------------------------

    @staticmethod
    def _eastern(dt: Optional[datetime]) -> Optional[datetime]:
        return to_eastern(dt)

    @staticmethod
    def _match_window(match: Match) -> Optional[Tuple[datetime, datetime]]:
        if not match.scheduled_at:
            return None
        scheduled = ReportsService._eastern(match.scheduled_at)
        if match.seated_at:
            start = ReportsService._eastern(match.seated_at)
        else:
            start = scheduled - timedelta(hours=1)
        if match.finished_at:
            end = ReportsService._eastern(match.finished_at)
        else:
            duration = DEFAULT_MATCH_DURATION_MIN
            if match.tournament_id and match.tournament and match.tournament.average_match_duration:
                duration = match.tournament.average_match_duration
            anchor = ReportsService._eastern(match.started_at) if match.started_at else scheduled
            end = anchor + timedelta(minutes=duration)
        if end < start:
            end = start
        return start, end

    @staticmethod
    def _auto_interval_minutes(start: datetime, end: datetime) -> int:
        span = end - start
        if span <= timedelta(hours=24):
            return 15
        if span <= timedelta(hours=72):
            return 30
        return 60

    async def generate_capacity_forecast(
        self,
        start: datetime,
        end: datetime,
        tournament_id: Optional[int] = None,
    ) -> Dict:
        """Compute concurrent-player counts at intervals across [start, end]."""
        start = self._eastern(start)
        end = self._eastern(end)
        if end < start:
            end = start
        interval_min = self._auto_interval_minutes(start, end)

        query = Match.all().filter(
            scheduled_at__gte=start - timedelta(hours=24),
            scheduled_at__lte=end + timedelta(hours=24),
            tenant_id=require_tenant_id(),
        )
        if tournament_id:
            query = query.filter(tournament_id=tournament_id)
        matches = await query.prefetch_related('tournament', 'players', 'stream_room')

        windows: List[Tuple[datetime, datetime, int, Match]] = []
        for match in matches:
            window = self._match_window(match)
            if not window:
                continue
            ws, we = window
            if we < start or ws > end:
                continue
            player_count = len(match.players)
            if player_count == 0 and match.tournament_id and match.tournament:
                player_count = match.tournament.players_per_match or 0
            windows.append((ws, we, player_count, match))

        intervals: List[datetime] = []
        player_counts: List[int] = []
        on_stream_counts: List[int] = []
        match_ids_per_interval: List[List[int]] = []

        current = start
        while current <= end:
            active = 0
            on_stream = 0
            ids: List[int] = []
            for ws, we, count, match in windows:
                if ws <= current <= we:
                    active += count
                    if match.stream_room_id:
                        on_stream += count
                    ids.append(match.id)
            intervals.append(current)
            player_counts.append(active)
            on_stream_counts.append(on_stream)
            match_ids_per_interval.append(ids)
            current += timedelta(minutes=interval_min)

        max_capacity = await SystemConfigService.get_max_concurrent_players()

        return {
            'intervals': intervals,
            'player_counts': player_counts,
            'on_stream_player_counts': on_stream_counts,
            'match_ids_per_interval': match_ids_per_interval,
            'interval_minutes': interval_min,
            'start': start,
            'end': end,
            'max_capacity': max_capacity,
        }

    @staticmethod
    def peak_times(
        intervals: List[datetime],
        counts: List[int],
        top_n: int = 5,
    ) -> List[Tuple[datetime, int]]:
        return sorted(zip(intervals, counts), key=lambda x: x[1], reverse=True)[:top_n]

    async def matches_active_at(
        self,
        instant: datetime,
        tournament_id: Optional[int] = None,
    ) -> List[Match]:
        instant = self._eastern(instant)
        query = Match.all().filter(
            scheduled_at__gte=instant - timedelta(hours=24),
            scheduled_at__lte=instant + timedelta(hours=24),
            tenant_id=require_tenant_id(),
        )
        if tournament_id:
            query = query.filter(tournament_id=tournament_id)
        matches = await query.prefetch_related('tournament', 'players', 'players__user', 'stream_room')
        out: List[Match] = []
        for match in matches:
            window = self._match_window(match)
            if not window:
                continue
            ws, we = window
            if ws <= instant <= we:
                out.append(match)
        return out

    # --- Match Operations --------------------------------------------------

    async def match_operations(
        self,
        start: datetime,
        end: datetime,
        tournament_id: Optional[int] = None,
    ) -> Dict:
        start = self._eastern(start)
        end = self._eastern(end)
        query = Match.all().filter(
            scheduled_at__gte=start,
            scheduled_at__lte=end,
            tenant_id=require_tenant_id(),
        )
        if tournament_id:
            query = query.filter(tournament_id=tournament_id)
        matches = await query.prefetch_related('tournament', 'stream_room', 'players')

        rows: List[Dict] = []
        per_tournament: Dict[int, Dict] = {}
        for match in matches:
            scheduled = self._eastern(match.scheduled_at)
            started = self._eastern(match.started_at)
            finished = self._eastern(match.finished_at)
            confirmed = self._eastern(match.confirmed_at)

            start_delay = None
            if scheduled and started:
                start_delay = int((started - scheduled).total_seconds() / 60)
            duration = None
            if started and finished:
                duration = int((finished - started).total_seconds() / 60)
            confirmation_lag = None
            if finished and confirmed:
                confirmation_lag = int((confirmed - finished).total_seconds() / 60)

            rows.append({
                'match_id': match.id,
                'tournament_id': match.tournament_id,
                'tournament_name': match.tournament.name if match.tournament else '',
                'scheduled_at': scheduled,
                'state': match.current_state,
                'stream_room': match.stream_room.name if match.stream_room else '',
                'start_delay_min': start_delay,
                'duration_min': duration,
                'confirmation_lag_min': confirmation_lag,
                'player_count': len(match.players),
            })

            t_id = match.tournament_id
            stats = per_tournament.setdefault(t_id, {
                'tournament_id': t_id,
                'tournament_name': match.tournament.name if match.tournament else '',
                'expected_avg_min': match.tournament.average_match_duration if match.tournament else None,
                'matches_total': 0,
                'matches_started': 0,
                'matches_finished': 0,
                'start_delay_total': 0,
                'duration_total': 0,
                'on_time_count': 0,
                '_duration_seen': 0,
                '_start_delay_seen': 0,
            })
            stats['matches_total'] += 1
            if start_delay is not None:
                stats['matches_started'] += 1
                stats['start_delay_total'] += start_delay
                stats['_start_delay_seen'] += 1
                if abs(start_delay) <= ON_TIME_THRESHOLD_MIN:
                    stats['on_time_count'] += 1
            if duration is not None:
                stats['matches_finished'] += 1
                stats['duration_total'] += duration
                stats['_duration_seen'] += 1

        aggregates: List[Dict] = []
        for stats in per_tournament.values():
            avg_delay = (stats['start_delay_total'] / stats['_start_delay_seen']) if stats['_start_delay_seen'] else None
            avg_duration = (stats['duration_total'] / stats['_duration_seen']) if stats['_duration_seen'] else None
            on_time_pct = (stats['on_time_count'] / stats['_start_delay_seen'] * 100) if stats['_start_delay_seen'] else None
            aggregates.append({
                'tournament_id': stats['tournament_id'],
                'tournament_name': stats['tournament_name'],
                'matches_total': stats['matches_total'],
                'matches_started': stats['matches_started'],
                'matches_finished': stats['matches_finished'],
                'avg_start_delay_min': round(avg_delay, 1) if avg_delay is not None else None,
                'avg_duration_min': round(avg_duration, 1) if avg_duration is not None else None,
                'expected_avg_min': stats['expected_avg_min'],
                'on_time_pct': round(on_time_pct, 1) if on_time_pct is not None else None,
            })

        return {'rows': rows, 'aggregates': aggregates}

    # --- Staff / Crew Activity ---------------------------------------------

    async def crew_coverage(
        self,
        start: datetime,
        end: datetime,
        tournament_id: Optional[int] = None,
        user_id: Optional[int] = None,
        approved_only: bool = False,
    ) -> Dict:
        start = self._eastern(start)
        end = self._eastern(end)

        match_query = Match.all().filter(
            scheduled_at__gte=start,
            scheduled_at__lte=end,
            tenant_id=require_tenant_id(),
        )
        if tournament_id:
            match_query = match_query.filter(tournament_id=tournament_id)
        matches = await match_query.prefetch_related(
            'tournament', 'stream_room',
            'commentators', 'commentators__user',
            'trackers', 'trackers__user',
        )

        coverage_rows: List[Dict] = []
        per_user: Dict[int, Dict] = {}
        for match in matches:
            comm_total = len(match.commentators)
            comm_approved = sum(1 for c in match.commentators if c.approved)
            trk_total = len(match.trackers)
            trk_approved = sum(1 for t in match.trackers if t.approved)

            include_match = True
            if user_id is not None:
                touched_by_user = any(c.user_id == user_id for c in match.commentators) or \
                                  any(t.user_id == user_id for t in match.trackers)
                include_match = touched_by_user

            if include_match:
                coverage_rows.append({
                    'match_id': match.id,
                    'tournament_name': match.tournament.name if match.tournament else '',
                    'scheduled_at': self._eastern(match.scheduled_at),
                    'stream_room': match.stream_room.name if match.stream_room else '',
                    'is_stream_candidate': match.is_stream_candidate,
                    'commentators_approved': comm_approved,
                    'commentators_total': comm_total,
                    'trackers_approved': trk_approved,
                    'trackers_total': trk_total,
                    'coverage_gap': match.is_stream_candidate and (comm_approved == 0 or trk_approved == 0),
                })

            duration_hours = 0.0
            if match.scheduled_at:
                window = self._match_window(match)
                if window:
                    ws, we = window
                    duration_hours = max(0.0, (we - ws).total_seconds() / 3600.0)

            def bump(entry, slot_total, slot_approved, hours) -> None:
                entry[f'{slot_total}_total'] += 1
                if not approved_only:
                    entry['hours_total'] += hours
                if slot_approved:
                    entry[f'{slot_total}_approved'] += 1
                    entry['hours_covered'] += hours

            for c in match.commentators:
                if user_id is not None and c.user_id != user_id:
                    continue
                entry = per_user.setdefault(c.user_id, _new_crew_entry(c.user))
                bump(entry, 'commentator', c.approved, duration_hours)

            for t in match.trackers:
                if user_id is not None and t.user_id != user_id:
                    continue
                entry = per_user.setdefault(t.user_id, _new_crew_entry(t.user))
                bump(entry, 'tracker', t.approved, duration_hours)

        contribution_rows = []
        for entry in per_user.values():
            contribution_rows.append({
                'user_id': entry['user_id'],
                'name': entry['name'],
                'commentator_approved': entry['commentator_approved'],
                'commentator_total': entry['commentator_total'],
                'tracker_approved': entry['tracker_approved'],
                'tracker_total': entry['tracker_total'],
                'hours_covered': round(entry['hours_covered'], 1),
                'hours_total': round(entry['hours_total'], 1),
            })
        contribution_rows.sort(key=lambda r: (-r['hours_covered'], r['name']))

        return {
            'coverage_rows': coverage_rows,
            'contribution_rows': contribution_rows,
        }

    # --- Stream Room Utilization ------------------------------------------

    async def stream_room_utilization(
        self,
        start: datetime,
        end: datetime,
        tournament_id: Optional[int] = None,
        stream_room_id: Optional[int] = None,
    ) -> Dict:
        start = self._eastern(start)
        end = self._eastern(end)

        rooms = await StreamRoom.filter(is_active=True, tenant_id=require_tenant_id()).order_by('name')
        if stream_room_id:
            rooms = [r for r in rooms if r.id == stream_room_id]

        match_query = Match.all().filter(
            scheduled_at__gte=start,
            scheduled_at__lte=end,
            tenant_id=require_tenant_id(),
        )
        if tournament_id:
            match_query = match_query.filter(tournament_id=tournament_id)
        matches = await match_query.prefetch_related('tournament', 'stream_room')

        unplaced_candidates = [
            m for m in matches
            if m.is_stream_candidate and m.stream_room_id is None
        ]

        per_room: Dict[int, Dict] = {}
        for room in rooms:
            per_room[room.id] = {
                'stream_room_id': room.id,
                'stream_room_name': room.name,
                'scheduled_hours': 0.0,
                'back_to_back_count': 0,
                'gap_hours': 0.0,
                'matches': [],
            }

        for match in matches:
            if match.stream_room_id is None or match.stream_room_id not in per_room:
                continue
            window = self._match_window(match)
            if not window:
                continue
            ws, we = window
            ws = max(ws, start)
            we = min(we, end)
            if we <= ws:
                continue
            block = per_room[match.stream_room_id]
            block['scheduled_hours'] += (we - ws).total_seconds() / 3600.0
            block['matches'].append({
                'match_id': match.id,
                'tournament_name': match.tournament.name if match.tournament else '',
                'start': ws,
                'end': we,
                'scheduled_at': self._eastern(match.scheduled_at),
            })

        for block in per_room.values():
            block['matches'].sort(key=lambda m: m['start'])
            prev_end = None
            gap_total = 0.0
            for m in block['matches']:
                if prev_end is not None:
                    gap = (m['start'] - prev_end).total_seconds() / 60.0
                    if gap < 15 and gap >= -1:
                        block['back_to_back_count'] += 1
                    if gap > 0:
                        gap_total += gap / 60.0
                prev_end = m['end']
            block['gap_hours'] = round(gap_total, 1)
            block['scheduled_hours'] = round(block['scheduled_hours'], 1)

        return {
            'rooms': list(per_room.values()),
            'unplaced_candidate_count': len(unplaced_candidates),
            'unplaced_candidates': unplaced_candidates,
        }


def _new_crew_entry(user: Optional[User]) -> Dict:
    return {
        'user_id': user.id if user else None,
        'name': (user.preferred_name if user else 'Unknown'),
        'commentator_approved': 0,
        'commentator_total': 0,
        'tracker_approved': 0,
        'tracker_total': 0,
        'hours_covered': 0.0,
        'hours_total': 0.0,
    }


def event_day_bounds(d: date) -> Tuple[datetime, datetime]:
    """Return midnight-to-next-midnight Eastern aware bounds for a date."""
    start = datetime.combine(d, time(0, 0), tzinfo=EASTERN_TZ)
    end = start + timedelta(days=1)
    return start, end
