"""
Volunteer Auto-schedule Service - Business Logic Layer

Greedy/heuristic draft generator. Fills open shift slots from the opted-in
volunteer pool using qualifications, availability, no-overlap, and hour
load-balancing. Produces ``auto_generated`` assignments the coordinator reviews.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Set, Tuple

from tortoise.transactions import in_transaction

from application.repositories import (
    VolunteerAssignmentRepository,
    VolunteerShiftRepository,
)
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.volunteer_availability_service import VolunteerAvailabilityService
from application.services.volunteer_profile_service import VolunteerProfileService
from application.services.volunteer_schedule_service import VolunteerScheduleService
from models import (
    User,
    VolunteerAvailabilityStatus,
    VolunteerQualification,
)


logger = logging.getLogger(__name__)

_AVAIL_RANK = {
    VolunteerAvailabilityStatus.PREFERRED: 0,
    VolunteerAvailabilityStatus.AVAILABLE: 1,
    None: 2,
}


class VolunteerAutoscheduleService:
    """Builds a draft volunteer schedule from availability + qualifications."""

    def __init__(self) -> None:
        self.shift_repository = VolunteerShiftRepository()
        self.assignment_repository = VolunteerAssignmentRepository()
        self.profile_service = VolunteerProfileService()
        self.availability_service = VolunteerAvailabilityService()
        self.schedule_service = VolunteerScheduleService()
        self.audit_service = AuditService()

    async def generate_draft(
        self,
        actor: User,
        start: datetime,
        end: datetime,
        *,
        position_ids: Optional[Sequence[int]] = None,
        clear_existing_drafts: bool = True,
    ) -> Dict:
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can auto-fill the schedule.",
        )

        if clear_existing_drafts:
            await self.assignment_repository.delete_auto_for_window(start, end)

        shifts = await self.shift_repository.list_for_window(start, end)
        if position_ids:
            allowed = set(position_ids)
            shifts = [s for s in shifts if s.position_id in allowed]
        shifts.sort(key=lambda s: (s.starts_at, s.id))

        pool = await self.profile_service.assignable_volunteers()
        if not pool:
            empty = {s.id: len(s.assignments) for s in shifts}
            return {'created': 0, 'unfilled': self._unfilled_summary(shifts, empty), 'pool_size': 0}
        pool_ids = [u.id for u in pool]

        quals = await self._qualifications(pool_ids)
        avail_map = await self.availability_service.availability_map(pool_ids, start, end)

        # Seed per-user state from assignments already in the window (manual + draft).
        intervals: Dict[int, List[Tuple[datetime, datetime]]] = {uid: [] for uid in pool_ids}
        hours: Dict[int, float] = {uid: 0.0 for uid in pool_ids}
        on_shift: Dict[int, Set[int]] = {uid: set() for uid in pool_ids}
        for a in await self.assignment_repository.list_for_window(start, end):
            if a.user_id in intervals:
                intervals[a.user_id].append((a.shift.starts_at, a.shift.ends_at))
                hours[a.user_id] += self._hours(a.shift.starts_at, a.shift.ends_at)
                on_shift[a.user_id].add(a.shift_id)

        created = 0
        filled_counts: Dict[int, int] = {}
        async with in_transaction():
            for shift in shifts:
                filled = len(shift.assignments)
                shift_hours = self._hours(shift.starts_at, shift.ends_at)
                for _ in range(shift.slots_needed - filled):
                    candidate = self._pick(
                        shift, pool, pool_ids, quals, avail_map, intervals, hours, on_shift,
                    )
                    if candidate is None:
                        break
                    await self.assignment_repository.create(
                        shift_id=shift.id, user_id=candidate.id,
                        assigned_by_id=actor.id, auto_generated=True,
                    )
                    intervals[candidate.id].append((shift.starts_at, shift.ends_at))
                    hours[candidate.id] += shift_hours
                    on_shift[candidate.id].add(shift.id)
                    filled += 1
                    created += 1
                filled_counts[shift.id] = filled

            await self.audit_service.write_log(
                actor, AuditActions.VOLUNTEER_DRAFT_GENERATED,
                {'created': created, 'start': start, 'end': end},
            )

        return {
            'created': created,
            'unfilled': self._unfilled_summary(shifts, filled_counts),
            'pool_size': len(pool),
        }

    async def clear_draft(self, actor: User, start: datetime, end: datetime) -> int:
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can clear drafts.",
        )
        removed = await self.assignment_repository.delete_auto_for_window(start, end)
        await self.audit_service.write_log(
            actor, AuditActions.VOLUNTEER_DRAFT_CLEARED,
            {'removed': removed, 'start': start, 'end': end},
        )
        return removed

    # --- internals --------------------------------------------------------

    def _pick(
        self, shift, pool, pool_ids, quals, avail_map, intervals, hours, on_shift,
    ) -> Optional[User]:
        best: Optional[User] = None
        best_key = None
        for user in pool:
            uid = user.id
            if shift.id in on_shift[uid]:
                continue
            qualified_set = quals.get(uid, set())
            if qualified_set and shift.position_id not in qualified_set:
                continue
            windows = avail_map.get(uid, [])
            status = VolunteerAvailabilityService.covers(windows, shift.starts_at, shift.ends_at)
            if status == VolunteerAvailabilityStatus.UNAVAILABLE:
                continue
            if self._overlaps(intervals[uid], shift.starts_at, shift.ends_at):
                continue
            qual_priority = 0 if shift.position_id in qualified_set else 1
            key = (qual_priority, _AVAIL_RANK.get(status, 2), hours[uid], user.preferred_name.lower())
            if best_key is None or key < best_key:
                best_key = key
                best = user
        return best

    @staticmethod
    def _overlaps(existing: List[Tuple[datetime, datetime]], start: datetime, end: datetime) -> bool:
        return any(s < end and e > start for s, e in existing)

    @staticmethod
    def _hours(start: datetime, end: datetime) -> float:
        return max(0.0, (end - start).total_seconds() / 3600.0)

    @staticmethod
    async def _qualifications(user_ids: List[int]) -> Dict[int, Set[int]]:
        rows = await VolunteerQualification.filter(user_id__in=user_ids).values_list(
            'user_id', 'position_id',
        )
        out: Dict[int, Set[int]] = {}
        for uid, pid in rows:
            out.setdefault(uid, set()).add(pid)
        return out

    @staticmethod
    def _unfilled_summary(shifts, filled_counts: Dict[int, int]) -> List[Dict]:
        out: List[Dict] = []
        for shift in shifts:
            filled = filled_counts.get(shift.id, len(shift.assignments))
            if filled < shift.slots_needed:
                out.append({
                    'shift_id': shift.id,
                    'position': shift.position.name if shift.position else '',
                    'open': shift.slots_needed - filled,
                })
        return out
