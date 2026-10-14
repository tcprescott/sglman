"""
Emergency Contact Repository - Data Access Layer

Handles database operations for members' emergency contacts.
"""

from typing import Optional

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id
from models import EmergencyContact, User


class EmergencyContactRepository(TenantScopedRepository[EmergencyContact]):
    """Repository for emergency contact data access."""

    model = EmergencyContact

    @staticmethod
    async def get_for_user(user_id: int) -> Optional[EmergencyContact]:
        return await EmergencyContact.get_or_none(
            user_id=user_id, tenant_id=current_tenant_id(),
        ).prefetch_related('last_viewed_by')

    @staticmethod
    async def create_for(user: User, **fields) -> EmergencyContact:
        return await EmergencyContact.create(
            tenant_id=current_tenant_id(), user=user, **fields,
        )
