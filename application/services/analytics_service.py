"""
Analytics Service - Business Logic Layer

Longitudinal / cross-event analytics that complement the point-in-time
snapshots in :class:`ReportsService`. Where the reports answer "what does the
schedule look like right now", these answer "how are things trending over
time" and "how healthy is each tournament".

All time math runs in US/Eastern. Events are bucketed by the Eastern calendar
date of when they happened (match ``scheduled_at``, shift ``starts_at``, audit
``created_at``) into weekly or monthly buckets.

Like :class:`ReportsService`, this queries the ORM models directly rather than
going through repositories — the aggregations are read-only and self-contained.
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from application.utils.timezone import now_eastern, to_eastern
from models import AuditLog, Match, VolunteerShift


ON_TIME_THRESHOLD_MIN = 5
DEFAULT_MATCH_DURATION_MIN = 90

# Weights for the composite tournament-health score. Components with no data
# (e.g. no stream candidates) are dropped and the remaining weights renormalize,
# so a tournament is never punished for a dimension that does not apply to it.
HEALTH_WEIGHTS = {
    'completion': 0.30,
    'on_time': 0.25,
    'coverage': 0.25,
    'duration': 0.20,
}

# Buckets wider than this are refused to avoid pathologically large series from
# an accidental multi-year weekly range.
MAX_BUCKETS = 240


class AnalyticsService:
    """Trend and health aggregations over matches, crew, volunteers, audit logs."""

    # --- Pure bucketing helpers -------------------------------------------

    @staticmethod
    def _eastern(dt: Optional[datetime]) -> Optional[datetime]:
        return to_eastern(dt)

    @staticmethod
    def bucket_start(d: date, bucket: str) -> date:
        """Snap a date to the first day of its containing bucket.

        Weekly buckets start on Monday; monthly buckets on the 1st.
        """
        if bucket == 'month':
            return d.replace(day=1)
        return d - timedelta(days=d.weekday())

    @staticmethod
    def _next_bucket(d: date, bucket: str) -> date:
        if bucket == 'month':
            year = d.year + (d.month // 12)
            month = d.month % 12 + 1
            return date(year, month, 1)
        return d + timedelta(days=7)

    @classmethod
    def iter_bucket_starts(
        cls, start: date, end: date, bucket: str
    ) -> List[date]:
        """Contiguous bucket-start dates covering ``[start, end]`` inclusive."""
        if end < start:
            end = start
        cursor = cls.bucket_start(start, bucket)
        last = cls.bucket_start(end, bucket)
        out: List[date] = []
        while cursor <= last and len(out) < MAX_BUCKETS:
            out.append(cursor)
            cursor = cls._next_bucket(cursor, bucket)
        return out

    @staticmethod
    def bucket_label(d: date, bucket: str) -> str:
        """Human label for a bucket start (``2025-10`` monthly, ISO date weekly)."""
        if bucket == 'month':
            return d.strftime('%Y-%m')
        return d.isoformat()

    @classmethod
    def _index_map(cls, bucket_starts: Sequence[date], bucket: str) -> Dict[date, int]:
        return {d: i for i, d in enumerate(bucket_starts)}

    @classmethod
    def _bucket_index(
        cls,
        index_map: Dict[date, int],
        instant: Optional[datetime],
        bucket: str,
    ) -> Optional[int]:
        """Return the series position for an event instant, or None if out of range."""
        if instant is None:
            return None
        eastern = to_eastern(instant)
        key = cls.bucket_start(eastern.date(), bucket)
        return index_map.get(key)

    @staticmethod
    def health_score(components: Sequence[Tuple[float, float]]) -> Optional[float]:
        """Weighted average of ``(value, weight)`` pairs, scaled to 0–100.

        ``value`` is expected in ``[0, 1]``. Returns ``None`` when no component
        has data so the caller can render "—" instead of a misleading zero.
        """
        present = [(v, w) for v, w in components if v is not None and w > 0]
        if not present:
            return None
        total_weight = sum(w for _, w in present)
        if total_weight <= 0:
            return None
        score = sum(max(0.0, min(1.0, v)) * w for v, w in present) / total_weight
        return round(score * 100, 1)

    @staticmethod
    def _normalize_bucket(bucket: Optional[str]) -> str:
        return 'month' if bucket == 'month' else 'week'

    # --- Crew participation trends ----------------------------------------

    async def crew_participation_trends(
        self,
        start: datetime,
        end: datetime,
        bucket: str = 'week',
        tournament_id: Optional[int] = None,
    ) -> Dict:
        """Commentator/tracker signups & approvals per time bucket.

        Participation is bucketed by the match's ``scheduled_at`` (when the work
        happens), not the signup timestamp.
        """
        bucket = self._normalize_bucket(bucket)
        start = self._eastern(start)
        end = self._eastern(end)
        bucket_starts = self.iter_bucket_starts(start.date(), end.date(), bucket)
        index_map = self._index_map(bucket_starts, bucket)
        n = len(bucket_starts)

        query = Match.all().filter(scheduled_at__gte=start, scheduled_at__lte=end)
        if tournament_id:
            query = query.filter(tournament_id=tournament_id)
        matches = await query.prefetch_related(
            'commentators', 'commentators__user',
            'trackers', 'trackers__user',
        )

        commentator_signups = [0] * n
        commentator_approved = [0] * n
        tracker_signups = [0] * n
        tracker_approved = [0] * n
        people_per_bucket: List[set] = [set() for _ in range(n)]
        contributors: Dict[int, Dict] = {}

        for match in matches:
            idx = self._bucket_index(index_map, match.scheduled_at, bucket)
            if idx is None:
                continue
            for c in match.commentators:
                commentator_signups[idx] += 1
                people_per_bucket[idx].add(c.user_id)
                entry = contributors.setdefault(c.user_id, _new_contributor(c.user))
                if c.approved:
                    commentator_approved[idx] += 1
                    entry['commentator_approved'] += 1
                    entry['total_approved'] += 1
            for t in match.trackers:
                tracker_signups[idx] += 1
                people_per_bucket[idx].add(t.user_id)
                entry = contributors.setdefault(t.user_id, _new_contributor(t.user))
                if t.approved:
                    tracker_approved[idx] += 1
                    entry['tracker_approved'] += 1
                    entry['total_approved'] += 1

        top_contributors = sorted(
            contributors.values(),
            key=lambda e: (-e['total_approved'], e['name']),
        )[:15]

        return {
            'bucket': bucket,
            'bucket_starts': bucket_starts,
            'bucket_labels': [self.bucket_label(d, bucket) for d in bucket_starts],
            'commentator_signups': commentator_signups,
            'commentator_approved': commentator_approved,
            'tracker_signups': tracker_signups,
            'tracker_approved': tracker_approved,
            'unique_people': [len(s) for s in people_per_bucket],
            'top_contributors': top_contributors,
            'totals': {
                'commentator_signups': sum(commentator_signups),
                'commentator_approved': sum(commentator_approved),
                'tracker_signups': sum(tracker_signups),
                'tracker_approved': sum(tracker_approved),
                'unique_people': len(contributors),
            },
        }

    # --- Volunteer hour trends --------------------------------------------

    async def volunteer_hour_trends(
        self,
        start: datetime,
        end: datetime,
        bucket: str = 'week',
    ) -> Dict:
        """Scheduled vs checked-in volunteer hours per time bucket.

        A shift contributes ``duration_hours × assignees`` scheduled hours to the
        bucket of its ``starts_at``; checked-in hours only count assignments that
        were actually checked in. Needed hours use ``slots_needed`` for fill rate.
        """
        bucket = self._normalize_bucket(bucket)
        start = self._eastern(start)
        end = self._eastern(end)
        bucket_starts = self.iter_bucket_starts(start.date(), end.date(), bucket)
        index_map = self._index_map(bucket_starts, bucket)
        n = len(bucket_starts)

        shifts = await VolunteerShift.all().filter(
            starts_at__gte=start, starts_at__lte=end,
        ).prefetch_related('position', 'assignments', 'assignments__user')

        scheduled_hours = [0.0] * n
        checked_in_hours = [0.0] * n
        needed_hours = [0.0] * n
        per_position: Dict[int, Dict] = {}
        per_user: Dict[int, Dict] = {}

        for shift in shifts:
            idx = self._bucket_index(index_map, shift.starts_at, bucket)
            if idx is None:
                continue
            duration_h = self._duration_hours(shift.starts_at, shift.ends_at)
            assignments = list(shift.assignments)
            filled = len(assignments)
            checked_in = sum(1 for a in assignments if a.checked_in_at is not None)

            scheduled_hours[idx] += duration_h * filled
            checked_in_hours[idx] += duration_h * checked_in
            needed_hours[idx] += duration_h * max(shift.slots_needed, filled)

            position = shift.position
            pos_entry = per_position.setdefault(position.id, {
                'position_id': position.id,
                'name': position.name,
                'color': position.color,
                'hours': [0.0] * n,
            })
            pos_entry['hours'][idx] += duration_h * filled

            for a in assignments:
                u_entry = per_user.setdefault(a.user_id, _new_volunteer(a.user))
                u_entry['scheduled_hours'] += duration_h
                u_entry['shifts'] += 1
                if a.checked_in_at is not None:
                    u_entry['checked_in_hours'] += duration_h

        top_volunteers = sorted(
            per_user.values(),
            key=lambda e: (-e['scheduled_hours'], e['name']),
        )[:15]
        for entry in top_volunteers:
            entry['scheduled_hours'] = round(entry['scheduled_hours'], 1)
            entry['checked_in_hours'] = round(entry['checked_in_hours'], 1)

        positions = sorted(per_position.values(), key=lambda p: p['name'])
        for pos in positions:
            pos['hours'] = [round(h, 1) for h in pos['hours']]

        return {
            'bucket': bucket,
            'bucket_starts': bucket_starts,
            'bucket_labels': [self.bucket_label(d, bucket) for d in bucket_starts],
            'scheduled_hours': [round(h, 1) for h in scheduled_hours],
            'checked_in_hours': [round(h, 1) for h in checked_in_hours],
            'needed_hours': [round(h, 1) for h in needed_hours],
            'fill_rate': [
                round(scheduled_hours[i] / needed_hours[i] * 100, 1)
                if needed_hours[i] > 0 else None
                for i in range(n)
            ],
            'positions': positions,
            'top_volunteers': top_volunteers,
            'totals': {
                'scheduled_hours': round(sum(scheduled_hours), 1),
                'checked_in_hours': round(sum(checked_in_hours), 1),
                'needed_hours': round(sum(needed_hours), 1),
                'volunteers': len(per_user),
            },
        }

    # --- Tournament health -------------------------------------------------

    async def tournament_health(
        self,
        start: datetime,
        end: datetime,
    ) -> Dict:
        """Per-tournament health scorecards for matches scheduled in the window.

        Completion is measured only against matches whose scheduled time has
        already passed, so upcoming matches never drag a score down.
        """
        start = self._eastern(start)
        end = self._eastern(end)
        now = now_eastern()

        matches = await Match.all().filter(
            scheduled_at__gte=start, scheduled_at__lte=end,
        ).prefetch_related('tournament', 'commentators', 'trackers')

        per_tournament: Dict[int, Dict] = {}
        for match in matches:
            t = match.tournament
            if t is None:
                continue
            stats = per_tournament.setdefault(t.id, {
                'tournament_id': t.id,
                'tournament_name': t.name,
                'expected_avg_min': t.average_match_duration,
                'matches_total': 0,
                'matches_past': 0,
                'matches_started': 0,
                'matches_finished': 0,
                'on_time_count': 0,
                '_start_delay_sum': 0,
                '_start_delay_seen': 0,
                '_duration_sum': 0,
                '_duration_seen': 0,
                'stream_candidates': 0,
                'candidates_covered': 0,
            })

            scheduled = self._eastern(match.scheduled_at)
            started = self._eastern(match.started_at)
            finished = self._eastern(match.finished_at)

            stats['matches_total'] += 1
            if scheduled and scheduled < now:
                stats['matches_past'] += 1
            if started:
                stats['matches_started'] += 1
            if finished:
                stats['matches_finished'] += 1

            if scheduled and started:
                delay = int((started - scheduled).total_seconds() / 60)
                stats['_start_delay_sum'] += delay
                stats['_start_delay_seen'] += 1
                if abs(delay) <= ON_TIME_THRESHOLD_MIN:
                    stats['on_time_count'] += 1
            if started and finished:
                stats['_duration_sum'] += int((finished - started).total_seconds() / 60)
                stats['_duration_seen'] += 1

            if match.is_stream_candidate:
                stats['stream_candidates'] += 1
                comm_ok = any(c.approved for c in match.commentators)
                trk_ok = any(t.approved for t in match.trackers)
                if comm_ok and trk_ok:
                    stats['candidates_covered'] += 1

        rows: List[Dict] = []
        for stats in per_tournament.values():
            rows.append(self._finalize_health(stats))
        rows.sort(key=lambda r: (r['health_score'] is None, r['health_score'] or 0, r['tournament_name']))

        return {'rows': rows}

    @classmethod
    def _finalize_health(cls, stats: Dict) -> Dict:
        completion = (
            stats['matches_finished'] / stats['matches_past']
            if stats['matches_past'] > 0 else None
        )
        on_time = (
            stats['on_time_count'] / stats['_start_delay_seen']
            if stats['_start_delay_seen'] > 0 else None
        )
        coverage = (
            stats['candidates_covered'] / stats['stream_candidates']
            if stats['stream_candidates'] > 0 else None
        )
        avg_delay = (
            stats['_start_delay_sum'] / stats['_start_delay_seen']
            if stats['_start_delay_seen'] > 0 else None
        )
        avg_duration = (
            stats['_duration_sum'] / stats['_duration_seen']
            if stats['_duration_seen'] > 0 else None
        )
        expected = stats['expected_avg_min']
        duration_adherence = None
        if expected and avg_duration is not None and expected > 0:
            duration_adherence = 1 - min(1.0, abs(avg_duration - expected) / expected)

        score = cls.health_score([
            (completion, HEALTH_WEIGHTS['completion']),
            (on_time, HEALTH_WEIGHTS['on_time']),
            (coverage, HEALTH_WEIGHTS['coverage']),
            (duration_adherence, HEALTH_WEIGHTS['duration']),
        ])

        return {
            'tournament_id': stats['tournament_id'],
            'tournament_name': stats['tournament_name'],
            'matches_total': stats['matches_total'],
            'matches_past': stats['matches_past'],
            'matches_started': stats['matches_started'],
            'matches_finished': stats['matches_finished'],
            'completion_pct': round(completion * 100, 1) if completion is not None else None,
            'on_time_pct': round(on_time * 100, 1) if on_time is not None else None,
            'coverage_pct': round(coverage * 100, 1) if coverage is not None else None,
            'avg_start_delay_min': round(avg_delay, 1) if avg_delay is not None else None,
            'avg_duration_min': round(avg_duration, 1) if avg_duration is not None else None,
            'expected_avg_min': expected,
            'health_score': score,
        }

    # --- Admin activity trends --------------------------------------------

    async def activity_trends(
        self,
        start: datetime,
        end: datetime,
        bucket: str = 'week',
    ) -> Dict:
        """Audit-log action volume per bucket, grouped by action namespace.

        The category is the part of the ``verb.object`` action string before the
        dot (e.g. ``match``, ``crew``, ``tournament``).
        """
        bucket = self._normalize_bucket(bucket)
        start = self._eastern(start)
        end = self._eastern(end)
        bucket_starts = self.iter_bucket_starts(start.date(), end.date(), bucket)
        index_map = self._index_map(bucket_starts, bucket)
        n = len(bucket_starts)

        logs = await AuditLog.all().filter(
            created_at__gte=start, created_at__lte=end,
        ).only('id', 'action', 'created_at')

        per_category: Dict[str, List[int]] = {}
        total = 0
        for log in logs:
            idx = self._bucket_index(index_map, log.created_at, bucket)
            if idx is None:
                continue
            category = (log.action or 'other').split('.', 1)[0]
            series = per_category.setdefault(category, [0] * n)
            series[idx] += 1
            total += 1

        categories = [
            {'category': cat, 'counts': counts, 'total': sum(counts)}
            for cat, counts in sorted(
                per_category.items(), key=lambda kv: -sum(kv[1])
            )
        ]

        return {
            'bucket': bucket,
            'bucket_starts': bucket_starts,
            'bucket_labels': [self.bucket_label(d, bucket) for d in bucket_starts],
            'categories': categories,
            'total': total,
        }

    # --- Internal ----------------------------------------------------------

    @staticmethod
    def _duration_hours(starts_at: datetime, ends_at: datetime) -> float:
        if not starts_at or not ends_at:
            return 0.0
        hours = (ends_at - starts_at).total_seconds() / 3600.0
        return max(0.0, hours)


def _new_contributor(user) -> Dict:
    return {
        'user_id': user.id if user else None,
        'name': (user.preferred_name if user else 'Unknown'),
        'commentator_approved': 0,
        'tracker_approved': 0,
        'total_approved': 0,
    }


def _new_volunteer(user) -> Dict:
    return {
        'user_id': user.id if user else None,
        'name': (user.preferred_name if user else 'Unknown'),
        'scheduled_hours': 0.0,
        'checked_in_hours': 0.0,
        'shifts': 0,
    }
