"""
Volunteer Availability Service - Business Logic Layer

Self-service availability for opted-in volunteers, plus lookups the coordinator
picker uses to flag who is available for a given shift.
"""

from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from tortoise.transactions import in_transaction

from application.repositories import (
    VolunteerAvailabilityRepository,
    VolunteerProfileRepository,
)
from application.services.audit_service import AuditActions, AuditService
from models import User, VolunteerAvailability, VolunteerAvailabilityStatus


class VolunteerAvailabilityService:
    """Volunteer-declared availability windows."""

    def __init__(self) -> None:
        self.repository = VolunteerAvailabilityRepository()
        self.profile_repository = VolunteerProfileRepository()
        self.audit_service = AuditService()

    async def availability_for(self, user: User) -> List[VolunteerAvailability]:
        return await self.repository.list_for_user(user)

    async def set_windows(
        self,
        user: User,
        windows: Sequence[Tuple[datetime, datetime, VolunteerAvailabilityStatus, Optional[str]]],
    ) -> List[VolunteerAvailability]:
        """Replace the user's availability with the supplied windows (self-service)."""
        profile = await self.profile_repository.get_for_user(user)
        if not profile or profile.opted_in_at is None:
            raise ValueError("Opt in to volunteering before setting your availability.")

        for starts_at, ends_at, _status, _note in windows:
            if ends_at <= starts_at:
                raise ValueError("Each availability window must end after it starts.")

        async with in_transaction():
            await self.repository.delete_for_user(user)
            created: List[VolunteerAvailability] = []
            for starts_at, ends_at, status, note in windows:
                created.append(
                    await self.repository.create(
                        user=user, starts_at=starts_at, ends_at=ends_at,
                        status=status, note=note,
                    )
                )
            await self.audit_service.write_log(
                user, AuditActions.VOLUNTEER_AVAILABILITY_UPDATED,
                {'window_count': len(created)},
            )
        return created

    async def clear(self, user: User) -> None:
        await self.repository.delete_for_user(user)
        await self.audit_service.write_log(
            user, AuditActions.VOLUNTEER_AVAILABILITY_UPDATED, {'window_count': 0},
        )

    async def availability_map(
        self, user_ids: List[int], start: datetime, end: datetime,
    ) -> Dict[int, List[VolunteerAvailability]]:
        """Map user_id -> availability windows overlapping [start, end]."""
        rows = await self.repository.for_users_overlapping(user_ids, start, end)
        out: Dict[int, List[VolunteerAvailability]] = {}
        for row in rows:
            out.setdefault(row.user_id, []).append(row)
        return out

    @staticmethod
    def covers(
        windows: Sequence[VolunteerAvailability], start: datetime, end: datetime,
    ) -> Optional[VolunteerAvailabilityStatus]:
        """Return the strongest availability signal for a shift window.

        ``preferred`` beats ``available``; an overlapping ``unavailable`` window
        wins outright. Returns None when no window overlaps the shift.
        """
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

    @staticmethod
    def effective_segments(
        windows: Sequence[VolunteerAvailability], start: datetime, end: datetime,
    ) -> List[Tuple[datetime, datetime, Optional[VolunteerAvailabilityStatus]]]:
        """Split ``[start, end]`` into maximal segments of constant availability.

        Overlapping windows are resolved by :meth:`covers` precedence
        (unavailable > preferred > available). Segments with no overlapping
        window carry a ``None`` status. Adjacent segments of equal status are
        merged so the result is the minimal set of contiguous spans.
        """
        if end <= start:
            return []
        boundaries = {start, end}
        for w in windows:
            if w.ends_at > start and w.starts_at < end:
                boundaries.add(max(w.starts_at, start))
                boundaries.add(min(w.ends_at, end))
        points = sorted(boundaries)
        segments: List[Tuple[datetime, datetime, Optional[VolunteerAvailabilityStatus]]] = []
        for seg_start, seg_end in zip(points, points[1:]):
            status = VolunteerAvailabilityService.covers(windows, seg_start, seg_end)
            if segments and segments[-1][2] == status:
                segments[-1] = (segments[-1][0], seg_end, status)
            else:
                segments.append((seg_start, seg_end, status))
        return segments
