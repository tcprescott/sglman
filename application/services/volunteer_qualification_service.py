"""
Volunteer Qualification Service - Business Logic Layer

Manages which positions each volunteer is qualified to fill.
"""

from typing import List, Set

from application.repositories.volunteer_qualification_repository import VolunteerQualificationRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from models import User


class VolunteerQualificationService:
    """Read and set qualification records for individual volunteers."""

    def __init__(self):
        self.repository = VolunteerQualificationRepository()
        self.audit_service = AuditService()

    async def get_qualified_position_ids(self, user: User) -> Set[int]:
        return await self.repository.qualified_position_ids(user)

    async def set_qualifications(
        self,
        actor: User,
        user: User,
        position_ids: List[int],
    ) -> None:
        await AuthService.ensure(
            await AuthService.can_manage_volunteers(actor),
            "Only volunteer coordinators can manage qualifications.",
        )
        await self.repository.set_for_user(user, position_ids)
        await self.audit_service.write_log(
            actor,
            AuditActions.VOLUNTEER_QUALIFICATIONS_UPDATED,
            {'user_id': user.id, 'position_ids': sorted(position_ids)},
        )
