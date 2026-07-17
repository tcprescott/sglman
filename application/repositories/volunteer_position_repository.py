"""
VolunteerPosition Repository - Data Access Layer

Coordinator-defined volunteer positions/jobs.
"""

from typing import List, Optional

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id, scoped
from models import VolunteerPosition


class VolunteerPositionRepository(TenantScopedRepository[VolunteerPosition]):
    """Repository for volunteer positions."""

    model = VolunteerPosition

    @staticmethod
    async def list_all() -> List[VolunteerPosition]:
        return await scoped(VolunteerPosition.all()).order_by('display_order', 'name')

    @staticmethod
    async def list_active() -> List[VolunteerPosition]:
        return await scoped(VolunteerPosition.filter(is_active=True)).order_by('display_order', 'name')

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
            tenant_id=current_tenant_id(),
            name=name,
            description=description,
            color=color,
            display_order=display_order,
            is_active=is_active,
            shift_length_minutes=shift_length_minutes,
            stagger_minutes=stagger_minutes,
        )

