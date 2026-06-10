"""
PlayerAvailability Repository - Data Access Layer

Player self-declared availability windows.
"""

from datetime import datetime
from typing import List, Optional

from models import PlayerAvailability, User, VolunteerAvailabilityStatus


class PlayerAvailabilityRepository:
    """Repository for player availability windows."""

    @staticmethod
    async def get_by_id(availability_id: int) -> Optional[PlayerAvailability]:
        return await PlayerAvailability.get_or_none(id=availability_id).prefetch_related('user')

    @staticmethod
    async def list_for_user(user: User) -> List[PlayerAvailability]:
        return await PlayerAvailability.filter(user=user).order_by('starts_at')

    @staticmethod
    async def for_users_overlapping(
        user_ids: List[int], start: datetime, end: datetime,
    ) -> List[PlayerAvailability]:
        if not user_ids:
            return []
        return await PlayerAvailability.filter(
            user_id__in=user_ids, starts_at__lt=end, ends_at__gt=start,
        )

    @staticmethod
    async def create(
        user: User,
        starts_at: datetime,
        ends_at: datetime,
        status: VolunteerAvailabilityStatus = VolunteerAvailabilityStatus.AVAILABLE,
        note: Optional[str] = None,
    ) -> PlayerAvailability:
        return await PlayerAvailability.create(
            user=user, starts_at=starts_at, ends_at=ends_at, status=status, note=note,
        )

    @staticmethod
    async def delete(availability: PlayerAvailability) -> None:
        await availability.delete()

    @staticmethod
    async def delete_for_user(user: User) -> int:
        return await PlayerAvailability.filter(user=user).delete()

    @staticmethod
    async def has_any(user_ids: List[int]) -> set[int]:
        """Return subset of user_ids that have at least one availability window."""
        if not user_ids:
            return set()
        rows = await PlayerAvailability.filter(user_id__in=user_ids).distinct().values_list('user_id', flat=True)
        return set(rows)
