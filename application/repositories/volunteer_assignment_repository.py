"""
VolunteerAssignment Repository - Data Access Layer

Volunteers placed into shifts.
"""

from datetime import datetime
from typing import List, Optional

from models import User, VolunteerAssignment, VolunteerShift


_PREFETCH = ('user', 'shift', 'shift__position')


class VolunteerAssignmentRepository:
    """Repository for volunteer shift assignments."""

    @staticmethod
    async def get_by_id(assignment_id: int) -> Optional[VolunteerAssignment]:
        return await VolunteerAssignment.get_or_none(id=assignment_id).prefetch_related(*_PREFETCH)

    @staticmethod
    async def exists(shift_id: int, user_id: int) -> bool:
        return await VolunteerAssignment.filter(shift_id=shift_id, user_id=user_id).exists()

    @staticmethod
    async def create(
        shift_id: int,
        user_id: int,
        assigned_by_id: Optional[int] = None,
        auto_generated: bool = False,
    ) -> VolunteerAssignment:
        return await VolunteerAssignment.create(
            shift_id=shift_id,
            user_id=user_id,
            assigned_by_id=assigned_by_id,
            auto_generated=auto_generated,
        )

    @staticmethod
    async def delete(assignment: VolunteerAssignment) -> None:
        await assignment.delete()

    @staticmethod
    async def save(assignment: VolunteerAssignment) -> VolunteerAssignment:
        await assignment.save()
        return assignment

    @staticmethod
    async def overlapping_for_user(
        user_id: int, start: datetime, end: datetime, exclude_shift_id: Optional[int] = None,
    ) -> List[VolunteerAssignment]:
        """Assignments whose shift overlaps [start, end] for this user."""
        query = VolunteerAssignment.filter(
            user_id=user_id, shift__starts_at__lt=end, shift__ends_at__gt=start,
        )
        if exclude_shift_id is not None:
            query = query.exclude(shift_id=exclude_shift_id)
        return await query.prefetch_related(*_PREFETCH)

    @staticmethod
    async def list_for_user(user: User, upcoming_after: Optional[datetime] = None) -> List[VolunteerAssignment]:
        query = VolunteerAssignment.filter(user=user)
        if upcoming_after is not None:
            query = query.filter(shift__ends_at__gte=upcoming_after)
        return await query.order_by('shift__starts_at').prefetch_related(*_PREFETCH)

    @staticmethod
    async def list_for_window(start: datetime, end: datetime) -> List[VolunteerAssignment]:
        return await (
            VolunteerAssignment.filter(shift__starts_at__lt=end, shift__ends_at__gt=start)
            .prefetch_related(*_PREFETCH)
        )

    @staticmethod
    async def delete_auto_for_window(start: datetime, end: datetime) -> int:
        """Delete draft (auto-generated) assignments whose shift overlaps the window.

        Done in two steps (resolve shift ids, then delete by id) so it works on
        databases that don't support join-based DELETE (e.g. SQLite in tests).
        """
        shift_ids = await VolunteerShift.filter(
            starts_at__lt=end, ends_at__gt=start,
        ).values_list('id', flat=True)
        if not shift_ids:
            return 0
        return await VolunteerAssignment.filter(
            auto_generated=True, shift_id__in=list(shift_ids),
        ).delete()

    @staticmethod
    async def due_for_reminder(
        window_start: datetime, window_end: datetime,
    ) -> List[VolunteerAssignment]:
        """Un-reminded assignments whose shift starts within [window_start, window_end]."""
        return await (
            VolunteerAssignment.filter(
                reminder_sent_at__isnull=True,
                shift__starts_at__gte=window_start,
                shift__starts_at__lte=window_end,
            )
            .prefetch_related(*_PREFETCH)
        )
