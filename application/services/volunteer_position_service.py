"""
Volunteer Position Service - Business Logic Layer

CRUD for coordinator-defined volunteer positions/jobs.
"""

from typing import List, Optional

from application.repositories import VolunteerPositionRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import User, VolunteerPosition


class VolunteerPositionService:
    """Manage the arbitrary, coordinator-defined position list."""

    def __init__(self):
        self.repository = VolunteerPositionRepository()
        self.audit_service = AuditService()

    async def list_all(self) -> List[VolunteerPosition]:
        return await self.repository.list_all()

    async def list_active(self) -> List[VolunteerPosition]:
        return await self.repository.list_active()

    async def get(self, position_id: int) -> Optional[VolunteerPosition]:
        return await self.repository.get_by_id(position_id)

    async def create(
        self,
        actor: User,
        name: str,
        description: Optional[str] = None,
        color: Optional[str] = None,
        display_order: int = 0,
        is_active: bool = True,
    ) -> VolunteerPosition:
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can manage positions.",
        )
        name = (name or '').strip()
        if not name:
            raise ValueError("Position name is required.")
        if await VolunteerPosition.filter(name=name).exists():
            raise ValueError(f"A position named '{name}' already exists.")
        position = await self.repository.create(
            name=name, description=description, color=color,
            display_order=display_order, is_active=is_active,
        )
        await self.audit_service.write_log(
            actor, AuditActions.VOLUNTEER_POSITION_CREATED,
            {'position_id': position.id, 'name': name},
        )
        return position

    async def update(self, actor: User, position: VolunteerPosition, **fields) -> VolunteerPosition:
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can manage positions.",
        )
        if 'name' in fields:
            new_name = (fields['name'] or '').strip()
            if not new_name:
                raise ValueError("Position name is required.")
            if await VolunteerPosition.filter(name=new_name).exclude(id=position.id).exists():
                raise ValueError(f"A position named '{new_name}' already exists.")
            fields['name'] = new_name
        position = await self.repository.update(position, **fields)
        await self.audit_service.write_log(
            actor, AuditActions.VOLUNTEER_POSITION_UPDATED,
            {'position_id': position.id, 'fields': sorted(fields.keys())},
        )
        return position

    async def delete(self, actor: User, position: VolunteerPosition) -> None:
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can manage positions.",
        )
        position_id = position.id
        await self.repository.delete(position)
        await self.audit_service.write_log(
            actor, AuditActions.VOLUNTEER_POSITION_DELETED, {'position_id': position_id},
        )
