"""
VolunteerAssignment Repository - Data Access Layer

Volunteers placed into shifts.
"""

from datetime import datetime
from typing import List, Optional

from application.repositories._tenant import current_tenant_id, scoped
from models import User, VolunteerAssignment, VolunteerShift


_PREFETCH = ('user', 'shift', 'shift__position', 'assigned_by')

# Only for the volunteer's own card, which names who else is on the slot. Kept
# off _PREFETCH so every other caller does not pay for the extra two joins.
_PREFETCH_WITH_SHIFTMATES = _PREFETCH + ('shift__assignments', 'shift__assignments__user')


class VolunteerAssignmentRepository:
    """Repository for volunteer shift assignments."""

    @staticmethod
    async def get_by_id(assignment_id: int) -> Optional[VolunteerAssignment]:
        return await VolunteerAssignment.get_or_none(
            id=assignment_id, tenant_id=current_tenant_id(),
        ).prefetch_related(*_PREFETCH)

    @staticmethod
    async def get_for_shift_and_user(
        shift_id: int, user_id: int,
    ) -> Optional[VolunteerAssignment]:
        return await scoped(
            VolunteerAssignment.filter(shift_id=shift_id, user_id=user_id)
        ).prefetch_related(*_PREFETCH).first()

    @staticmethod
    async def exists(shift_id: int, user_id: int) -> bool:
        return await scoped(VolunteerAssignment.filter(shift_id=shift_id, user_id=user_id)).exists()

    @staticmethod
    async def create(
        shift_id: int,
        user_id: int,
        assigned_by_id: Optional[int] = None,
        auto_generated: bool = False,
    ) -> VolunteerAssignment:
        return await VolunteerAssignment.create(
            tenant_id=current_tenant_id(),
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
        query = scoped(VolunteerAssignment.filter(
            user_id=user_id, shift__starts_at__lt=end, shift__ends_at__gt=start,
        ))
        if exclude_shift_id is not None:
            query = query.exclude(shift_id=exclude_shift_id)
        return await query.prefetch_related(*_PREFETCH)

    @staticmethod
    async def list_for_user(
        user: User,
        upcoming_after: Optional[datetime] = None,
        *,
        include_drafts: bool = False,
        with_shiftmates: bool = False,
    ) -> List[VolunteerAssignment]:
        """This user's assignments.

        Drafts are excluded by default: an ``auto_generated`` row is the
        coordinator's sketch and the volunteer has not been told about it (see
        ``VolunteerAutoscheduleService.publish_draft``).
        """
        query = scoped(VolunteerAssignment.filter(user=user))
        if not include_drafts:
            query = query.filter(auto_generated=False)
        if upcoming_after is not None:
            query = query.filter(shift__ends_at__gte=upcoming_after)
        prefetch = _PREFETCH_WITH_SHIFTMATES if with_shiftmates else _PREFETCH
        return await query.order_by('shift__starts_at').prefetch_related(*prefetch)

    @staticmethod
    async def list_for_window(start: datetime, end: datetime) -> List[VolunteerAssignment]:
        return await (
            scoped(VolunteerAssignment.filter(shift__starts_at__lt=end, shift__ends_at__gt=start))
            .prefetch_related(*_PREFETCH)
        )

    @staticmethod
    async def delete_auto_for_window(start: datetime, end: datetime) -> int:
        """Delete draft (auto-generated) assignments whose shift overlaps the window.

        Done in two steps (resolve shift ids, then delete by id) so it works on
        databases that don't support join-based DELETE (e.g. SQLite in tests).
        """
        shift_ids = await scoped(VolunteerShift.filter(
            starts_at__lt=end, ends_at__gt=start,
        )).values_list('id', flat=True)
        if not shift_ids:
            return 0
        return await scoped(VolunteerAssignment.filter(
            auto_generated=True, shift_id__in=list(shift_ids),
        )).delete()

    @staticmethod
    async def count_auto_for_window(start: datetime, end: datetime) -> int:
        """How many draft assignments sit in the window."""
        shift_ids = await scoped(VolunteerShift.filter(
            starts_at__lt=end, ends_at__gt=start,
        )).values_list('id', flat=True)
        if not shift_ids:
            return 0
        return await scoped(VolunteerAssignment.filter(
            auto_generated=True, shift_id__in=list(shift_ids),
        )).count()

    @staticmethod
    async def list_auto_for_window(start: datetime, end: datetime) -> List[VolunteerAssignment]:
        """Draft assignments whose shift overlaps the window, prefetched for notification."""
        shift_ids = await scoped(VolunteerShift.filter(
            starts_at__lt=end, ends_at__gt=start,
        )).values_list('id', flat=True)
        if not shift_ids:
            return []
        return await (
            scoped(VolunteerAssignment.filter(
                auto_generated=True, shift_id__in=list(shift_ids),
            ))
            .order_by('shift__starts_at')
            .prefetch_related(*_PREFETCH)
        )

    @staticmethod
    async def mark_published(assignment: VolunteerAssignment) -> VolunteerAssignment:
        assignment.auto_generated = False
        await assignment.save(update_fields=['auto_generated', 'updated_at'])
        return assignment

    @staticmethod
    async def list_for_shift(shift_id: int) -> List[VolunteerAssignment]:
        return await (
            scoped(VolunteerAssignment.filter(shift_id=shift_id))
            .prefetch_related(*_PREFETCH)
        )

    @staticmethod
    async def due_for_reminder(
        window_start: datetime, window_end: datetime,
    ) -> List[VolunteerAssignment]:
        """Un-reminded assignments whose shift starts within [window_start, window_end].

        Drafts are skipped — the reminder must not be the message that first tells
        someone they have a shift.
        """
        # Deliberately cross-tenant: the reminder loop scans every tenant and wraps
        # each assignment in its own tenant_scope before acting. Do NOT scope this.
        return await (
            VolunteerAssignment.filter(
                auto_generated=False,
                reminder_sent_at__isnull=True,
                shift__starts_at__gte=window_start,
                shift__starts_at__lte=window_end,
            )
            .prefetch_related(*_PREFETCH)
        )
