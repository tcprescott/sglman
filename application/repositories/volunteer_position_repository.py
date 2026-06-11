"""
VolunteerPosition Repository - Data Access Layer

Coordinator-defined volunteer positions/jobs.
"""

from typing import List, Optional

from models import VolunteerPosition


class VolunteerPositionRepository:
    """Repository for volunteer positions."""

    @staticmethod
    async def get_by_id(position_id: int) -> Optional[VolunteerPosition]:
        return await VolunteerPosition.get_or_none(id=position_id)

    @staticmethod
    async def list_all() -> List[VolunteerPosition]:
        return await VolunteerPosition.all().order_by('display_order', 'name')

    @staticmethod
    async def list_active() -> List[VolunteerPosition]:
        return await VolunteerPosition.filter(is_active=True).order_by('display_order', 'name')

    @staticmethod
    async def create(
        name: str,
        description: Optional[str] = None,
        color: Optional[str] = None,
        display_order: int = 0,
        is_active: bool = True,
        shift_length_minutes: Optional[int] = None,
        stagger_minutes: Optional[int] = None,
    ) -> VolunteerPosition:
        return await VolunteerPosition.create(
            name=name,
            description=description,
            color=color,
            display_order=display_order,
            is_active=is_active,
            shift_length_minutes=shift_length_minutes,
            stagger_minutes=stagger_minutes,
        )

    @staticmethod
    async def update(position: VolunteerPosition, **fields) -> VolunteerPosition:
        for key, value in fields.items():
            setattr(position, key, value)
        await position.save()
        return position

    @staticmethod
    async def delete(position: VolunteerPosition) -> None:
        await position.delete()
