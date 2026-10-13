"""
Volunteer Pool Service - Business Logic Layer

The assignable-volunteer pool used by the coordinator UI, the auto-scheduler,
hours and the export. Membership comes from community roles alone.
"""

from typing import List

from application.tenant_context import require_tenant_id
from models import Role, User, UserRole

ASSIGNABLE_ROLES = (Role.VOLUNTEER, Role.STAFF)


class VolunteerPoolService:
    """Who coordinators can schedule: VOLUNTEER or STAFF role holders."""

    async def assignable_user_ids(self) -> set[int]:
        """Ids of every VOLUNTEER or STAFF role holder **in the current tenant**.

        Roles are per-tenant (``UserRole.tenant``), so scoping to the active
        tenant keeps another community's volunteers out of this coordinator's
        roster and auto-scheduler pool.
        """
        user_ids: list[int] = await UserRole.filter(  # type: ignore[assignment]
            role__in=ASSIGNABLE_ROLES, tenant_id=require_tenant_id(),
        ).values_list('user_id', flat=True)
        return set(user_ids)

    async def assignable_volunteers(self) -> List[User]:
        """The pool as users, by name."""
        user_ids = await self.assignable_user_ids()
        if not user_ids:
            return []
        users = await User.filter(id__in=user_ids)
        return sorted(users, key=lambda u: u.preferred_name.lower())
