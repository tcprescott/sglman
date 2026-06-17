"""
VolunteerShift Repository - Data Access Layer

Position-scoped, time-windowed shifts.
"""

from datetime import datetime
from typing import List, Optional

from models import VolunteerShift


_PREFETCH = ('position', 'assignments', 'assignments__user')


class VolunteerShiftRepository:
    """Repository for volunteer shifts."""

    @staticmethod
    async def get_by_id(shift_id: int) -> Optional[VolunteerShift]:
        return await VolunteerShift.get_or_none(id=shift_id).prefetch_related(*_PREFETCH)

    @staticmethod
    async def list_for_window(start: datetime, end: datetime) -> List[VolunteerShift]:
        """Shifts overlapping [start, end], ordered by position then start time."""
        return await (
            VolunteerShift.filter(starts_at__lt=end, ends_at__gt=start)
            .order_by('position__display_order', 'position__name', 'starts_at')
            .prefetch_related(*_PREFETCH)
        )

    @staticmethod
    async def list_for_position_window(
        position_id: int, start: datetime, end: datetime,
    ) -> List[VolunteerShift]:
        return await (
            VolunteerShift.filter(
                position_id=position_id, starts_at__lt=end, ends_at__gt=start,
            )
            .order_by('starts_at')
            .prefetch_related(*_PREFETCH)
        )

    @staticmethod
    async def create(
        position_id: int,
        starts_at: datetime,
        ends_at: datetime,
        label: Optional[str] = None,
        slots_needed: int = 1,
        notes: Optional[str] = None,
    ) -> VolunteerShift:
        return await VolunteerShift.create(
            position_id=position_id,
            starts_at=starts_at,
            ends_at=ends_at,
            label=label,
            slots_needed=slots_needed,
            notes=notes,
        )

    @staticmethod
    async def update(shift: VolunteerShift, **fields) -> VolunteerShift:
        for key, value in fields.items():
            setattr(shift, key, value)
        await shift.save()
        return shift

    @staticmethod
    async def delete(shift: VolunteerShift) -> None:
        await shift.delete()

    @staticmethod
    async def delete_all() -> int:
        return await VolunteerShift.all().delete()
