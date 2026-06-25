"""
Volunteer Schedule Service - Business Logic Layer

Shifts, assignments, acknowledgement, and coverage for the onsite volunteer
schedule. Coordinator-driven; mirrors the crew signup/approve/acknowledge flow
for Discord notifications.
"""

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from tortoise.transactions import in_transaction

from application.repositories import (
    VolunteerAssignmentRepository,
    VolunteerPositionRepository,
    VolunteerShiftRepository,
)
from application.services import discord_queue
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.discord_service import DiscordService
from application.utils.timezone import (
    EASTERN_TZ,
    format_eastern_display,
    parse_eastern_datetime,
    to_eastern,
)
from models import User, VolunteerAssignment, VolunteerPosition, VolunteerShift


logger = logging.getLogger(__name__)


class VolunteerScheduleService:
    """Core volunteer-scheduling operations."""

    def __init__(self) -> None:
        self.shift_repository = VolunteerShiftRepository()
        self.assignment_repository = VolunteerAssignmentRepository()
        self.position_repository = VolunteerPositionRepository()
        self.audit_service = AuditService()
        self.discord_service = DiscordService()

    # --- Shifts -----------------------------------------------------------

    async def list_shifts_for_window(self, start: datetime, end: datetime) -> List[VolunteerShift]:
        return await self.shift_repository.list_for_window(start, end)

    async def get_shift(self, shift_id: int) -> Optional[VolunteerShift]:
        return await self.shift_repository.get_by_id(shift_id)

    async def create_shift(
        self,
        actor: User,
        position_id: int,
        starts_at: datetime,
        ends_at: datetime,
        label: Optional[str] = None,
        slots_needed: int = 1,
        notes: Optional[str] = None,
    ) -> VolunteerShift:
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can manage shifts.",
        )
        if ends_at <= starts_at:
            raise ValueError("A shift must end after it starts.")
        if slots_needed < 1:
            raise ValueError("A shift needs at least one slot.")
        shift = await self.shift_repository.create(
            position_id=position_id, starts_at=starts_at, ends_at=ends_at,
            label=label, slots_needed=slots_needed, notes=notes,
        )
        await self.audit_service.write_log(
            actor, AuditActions.VOLUNTEER_SHIFT_CREATED,
            {'shift_id': shift.id, 'position_id': position_id},
        )
        return shift

    async def generate_day_shifts(
        self,
        actor: User,
        date_str: str,
        position_ids: Sequence[int],
        blocks: Sequence[Tuple[str, str, str]],
    ) -> List[VolunteerShift]:
        """Create shifts for one event day.

        ``blocks`` is a sequence of ``(label, start_hhmm, end_hhmm)`` in Eastern.
        A block whose end is at or before its start (e.g. 20:00–00:00) is treated
        as crossing midnight into the next day.

        Positions configured with ``shift_length_minutes``/``stagger_minutes``
        instead get staggered rolling shifts spanning the same overall day window
        (first block start → last block end), so their crew hands off one at a
        time rather than all together.
        """
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can manage shifts.",
        )
        created: List[VolunteerShift] = []
        async with in_transaction():
            for position_id in position_ids:
                position = await self.position_repository.get_by_id(position_id)
                if position is not None and position.is_staggered:
                    created.extend(
                        await self._generate_staggered(position, date_str, blocks)
                    )
                else:
                    created.extend(
                        await self._generate_blocks(position_id, date_str, blocks)
                    )
            await self.audit_service.write_log(
                actor, AuditActions.VOLUNTEER_SHIFT_CREATED,
                {'generated': len(created), 'date': date_str,
                 'position_ids': list(position_ids)},
            )
        return created

    async def _generate_blocks(
        self, position_id: int, date_str: str,
        blocks: Sequence[Tuple[str, str, str]],
    ) -> List[VolunteerShift]:
        """Create one fixed shift per block for a position."""
        out: List[VolunteerShift] = []
        for label, start_hhmm, end_hhmm in blocks:
            starts_at = parse_eastern_datetime(date_str, start_hhmm)
            ends_at = parse_eastern_datetime(date_str, end_hhmm)
            if ends_at <= starts_at:
                ends_at = ends_at + timedelta(days=1)
            out.append(
                await self.shift_repository.create(
                    position_id=position_id, starts_at=starts_at,
                    ends_at=ends_at, label=label or None,
                )
            )
        return out

    async def _generate_staggered(
        self, position: VolunteerPosition, date_str: str,
        blocks: Sequence[Tuple[str, str, str]],
    ) -> List[VolunteerShift]:
        """Create staggered rolling shifts spanning the day's coverage window."""
        coverage_start = parse_eastern_datetime(date_str, blocks[0][1])
        coverage_end = parse_eastern_datetime(date_str, blocks[-1][2])
        if coverage_end <= coverage_start:
            coverage_end = coverage_end + timedelta(days=1)
        shift_length = timedelta(minutes=position.shift_length_minutes)
        stagger = timedelta(minutes=position.stagger_minutes)
        out: List[VolunteerShift] = []
        cursor = coverage_start
        while cursor < coverage_end:
            ends_at = min(cursor + shift_length, coverage_end)
            out.append(
                await self.shift_repository.create(
                    position_id=position.id, starts_at=cursor, ends_at=ends_at,
                )
            )
            cursor += stagger
        return out

    async def update_shift(self, actor: User, shift: VolunteerShift, **fields) -> VolunteerShift:
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can manage shifts.",
        )
        starts = fields.get('starts_at', shift.starts_at)
        ends = fields.get('ends_at', shift.ends_at)
        if ends <= starts:
            raise ValueError("A shift must end after it starts.")
        if fields.get('slots_needed', shift.slots_needed) < 1:
            raise ValueError("A shift needs at least one slot.")
        shift = await self.shift_repository.update(shift, **fields)
        await self.audit_service.write_log(
            actor, AuditActions.VOLUNTEER_SHIFT_UPDATED, {'shift_id': shift.id},
        )
        return shift

    async def delete_shift(self, actor: User, shift: VolunteerShift) -> None:
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can manage shifts.",
        )
        shift_id = shift.id
        await self.shift_repository.delete(shift)
        await self.audit_service.write_log(
            actor, AuditActions.VOLUNTEER_SHIFT_DELETED, {'shift_id': shift_id},
        )

    async def reset_all_shifts(self, actor: User) -> int:
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can manage shifts.",
        )
        deleted = await self.shift_repository.delete_all()
        await self.audit_service.write_log(
            actor, AuditActions.VOLUNTEER_SHIFTS_RESET, {'deleted_count': deleted},
        )
        return deleted

    # --- Assignments ------------------------------------------------------

    async def assign(
        self,
        actor: User,
        shift: VolunteerShift,
        user: User,
        *,
        auto_generated: bool = False,
        notify: bool = True,
    ) -> Tuple[VolunteerAssignment, List[str]]:
        """Place ``user`` into ``shift``. Returns (assignment, soft warnings).

        Hard failures (already assigned, overlapping shift) raise ValueError.
        Soft conditions (overfilled, outside stated availability) are returned as
        warnings for the UI to surface but do not block.
        """
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can assign volunteers.",
        )
        if await self.assignment_repository.exists(shift.id, user.id):
            raise ValueError(f"{user.preferred_name} is already on this shift.")

        overlapping = await self.assignment_repository.overlapping_for_user(
            user.id, shift.starts_at, shift.ends_at, exclude_shift_id=shift.id,
        )
        if overlapping:
            raise ValueError(
                f"{user.preferred_name} is already assigned to an overlapping shift."
            )

        warnings: List[str] = []
        existing = await VolunteerAssignment.filter(shift_id=shift.id).count()
        if existing >= shift.slots_needed:
            warnings.append(
                f"This shift already has {existing}/{shift.slots_needed} slots filled."
            )

        availability_warning = await self._availability_warning(user, shift)
        if availability_warning:
            warnings.append(availability_warning)

        assignment = await self.assignment_repository.create(
            shift_id=shift.id, user_id=user.id,
            assigned_by_id=actor.id, auto_generated=auto_generated,
        )
        await self.audit_service.write_log(
            actor, AuditActions.VOLUNTEER_ASSIGNED,
            {'assignment_id': assignment.id, 'shift_id': shift.id,
             'user_id': user.id, 'auto_generated': auto_generated},
        )
        if notify and not auto_generated:
            await self._request_acknowledgment(assignment, shift, user)
        return assignment, warnings

    async def unassign(self, actor: User, assignment: VolunteerAssignment) -> None:
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can remove assignments.",
        )
        details = {
            'assignment_id': assignment.id,
            'shift_id': assignment.shift_id,
            'user_id': assignment.user_id,
        }
        await self.assignment_repository.delete(assignment)
        await self.audit_service.write_log(actor, AuditActions.VOLUNTEER_UNASSIGNED, details)

    async def acknowledge(self, assignment_id: int, user: User) -> VolunteerAssignment:
        """Self-acknowledge an assignment. Idempotent."""
        assignment = await self.assignment_repository.get_by_id(assignment_id)
        if assignment is None:
            raise ValueError("Volunteer assignment not found.")
        if assignment.user_id != user.id:
            raise ValueError("You can only acknowledge your own assignments.")
        if assignment.acknowledged_at is not None:
            return assignment
        assignment.acknowledged_at = datetime.now(EASTERN_TZ)
        await self.assignment_repository.save(assignment)
        await self.audit_service.write_log(
            user, AuditActions.VOLUNTEER_ACKNOWLEDGED,
            {'assignment_id': assignment.id, 'shift_id': assignment.shift_id},
        )
        return assignment

    async def check_in(self, assignment_id: int, actor: User) -> VolunteerAssignment:
        """Record that a volunteer appeared for their shift."""
        if not await AuthService.can_manage_volunteers(actor):
            raise PermissionError('Only coordinators and staff can record check-ins.')
        assignment = await self.assignment_repository.get_by_id(assignment_id)
        if assignment is None:
            raise ValueError('Assignment not found.')
        if assignment.checked_in_at is None:
            assignment.checked_in_at = datetime.now(timezone.utc)
            assignment.checked_in_by_id = actor.id
            await assignment.save()
            await self.audit_service.write_log(
                actor, AuditActions.VOLUNTEER_CHECKED_IN, {'assignment_id': assignment.id},
            )
        return assignment

    async def assignments_for_user(self, user: User, upcoming_after: Optional[datetime] = None) -> List[VolunteerAssignment]:
        return await self.assignment_repository.list_for_user(user, upcoming_after=upcoming_after)

    # --- Coverage ---------------------------------------------------------

    async def coverage(self, start: datetime, end: datetime) -> List[Dict]:
        """Per-shift filled/needed counts across [start, end]."""
        shifts = await self.shift_repository.list_for_window(start, end)
        rows: List[Dict] = []
        for shift in shifts:
            filled = len(shift.assignments)
            rows.append({
                'shift_id': shift.id,
                'position': shift.position.name if shift.position else '',
                'label': shift.label or '',
                'starts_at': shift.starts_at,
                'ends_at': shift.ends_at,
                'filled': filled,
                'needed': shift.slots_needed,
                'understaffed': filled < shift.slots_needed,
            })
        return rows

    # --- Helpers ----------------------------------------------------------

    async def _availability_warning(self, user: User, shift: VolunteerShift) -> Optional[str]:
        from application.services.volunteer_availability_service import (
            VolunteerAvailabilityService,
        )
        from models import VolunteerAvailabilityStatus

        svc = VolunteerAvailabilityService()
        windows = await svc.availability_for(user)
        status = VolunteerAvailabilityService.covers(windows, shift.starts_at, shift.ends_at)
        if status == VolunteerAvailabilityStatus.UNAVAILABLE:
            return f"{user.preferred_name} marked this time as unavailable."
        if status is None and windows:
            return f"{user.preferred_name} has not marked this time as available."
        return None

    async def _request_acknowledgment(
        self, assignment: VolunteerAssignment, shift: VolunteerShift, user: User,
    ) -> None:
        """Best-effort Discord DM asking the volunteer to confirm. Never raises."""
        from application.utils.discord_messages import volunteer_assignment_dm

        discord_id = getattr(user, 'discord_id', None)
        if not discord_id or not getattr(user, 'dm_notifications', True):
            return
        position_name = shift.position.name if shift.position else ''
        message = volunteer_assignment_dm(
            position_name=position_name,
            label=shift.label,
            starts_display=format_eastern_display(shift.starts_at),
            ends_display=format_eastern_display(shift.ends_at),
        )
        discord_queue.enqueue(
            self.discord_service.send_dm_with_volunteer_acknowledgment_button(
                int(discord_id), message, assignment.id,
            )
        )
