"""
VolunteerQualification Repository - Data Access Layer

Which positions a volunteer is qualified to fill.
"""

from typing import List, Set

from tortoise.transactions import in_transaction

from models import User, VolunteerQualification


class VolunteerQualificationRepository:
    """Repository for volunteer position qualifications."""

    @staticmethod
    async def qualified_position_ids(user: User) -> Set[int]:
        ids = await VolunteerQualification.filter(user=user).values_list('position_id', flat=True)
        return set(ids)

    @staticmethod
    async def set_for_user(user: User, position_ids: List[int]) -> None:
        """Replace all qualifications for ``user`` with the given position IDs."""
        async with in_transaction():
            await VolunteerQualification.filter(user=user).delete()
            for pid in position_ids:
                await VolunteerQualification.create(user_id=user.id, position_id=pid)

    @staticmethod
    async def qualified_user_ids_for_position(position_id: int) -> Set[int]:
        ids = await VolunteerQualification.filter(position_id=position_id).values_list('user_id', flat=True)
        return set(ids)

    @staticmethod
    async def list_all() -> List[VolunteerQualification]:
        return await VolunteerQualification.all().prefetch_related('user', 'position')
