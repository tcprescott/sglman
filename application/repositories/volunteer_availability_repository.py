"""
VolunteerAvailability Repository - Data Access Layer

Volunteer self-declared availability windows.
"""

from datetime import datetime
from typing import List, Optional

from models import User, VolunteerAvailability, VolunteerAvailabilityStatus


class VolunteerAvailabilityRepository:
    """Repository for volunteer availability windows."""

    @staticmethod
    async def get_by_id(availability_id: int) -> Optional[VolunteerAvailability]:
        return await VolunteerAvailability.get_or_none(id=availability_id).prefetch_related('user')

    @staticmethod
    async def list_for_user(user: User) -> List[VolunteerAvailability]:
        return await VolunteerAvailability.filter(user=user).order_by('starts_at')

    @staticmethod
    async def for_users_overlapping(
        user_ids: List[int], start: datetime, end: datetime,
    ) -> List[VolunteerAvailability]:
        if not user_ids:
            return []
        return await VolunteerAvailability.filter(
            user_id__in=user_ids, starts_at__lt=end, ends_at__gt=start,
        )

    @staticmethod
    async def create(
        user: User,
        starts_at: datetime,
        ends_at: datetime,
        status: VolunteerAvailabilityStatus = VolunteerAvailabilityStatus.AVAILABLE,
        note: Optional[str] = None,
    ) -> VolunteerAvailability:
        return await VolunteerAvailability.create(
            user=user, starts_at=starts_at, ends_at=ends_at, status=status, note=note,
        )

    @staticmethod
    async def delete(availability: VolunteerAvailability) -> None:
        await availability.delete()

    @staticmethod
    async def delete_for_user(user: User) -> int:
        return await VolunteerAvailability.filter(user=user).delete()
