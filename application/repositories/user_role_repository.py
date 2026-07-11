"""
UserRole Repository - Data Access Layer

Handles database operations for the userrole join table.

Roles are per-tenant, with one exception: ``SUPER_ADMIN`` is a global platform
role whose row carries ``tenant=NULL``. ``_tenant_id_for_role`` encodes that
invariant so every method scopes normal roles to the current tenant while
SUPER_ADMIN operations target the global (NULL-tenant) row.
"""

from typing import List, Optional

from application.repositories._tenant import current_tenant_id
from models import Role, RoleSource, User, UserRole


def _tenant_id_for_role(role: Role) -> Optional[int]:
    return None if role == Role.SUPER_ADMIN else current_tenant_id()


class UserRoleRepository:
    """Repository for UserRole data access."""

    @staticmethod
    async def add(
        user: User,
        role: Role,
        granted_by: Optional[User] = None,
        source: RoleSource = RoleSource.MANUAL,
    ) -> UserRole:
        tenant_id = _tenant_id_for_role(role)
        instance, created = await UserRole.get_or_create(
            user=user, role=role, tenant_id=tenant_id,
            defaults={'granted_by': granted_by, 'source': source},
        )
        # A manual grant pins the role so a later Discord sync won't revoke it.
        if not created and source == RoleSource.MANUAL and instance.source != RoleSource.MANUAL:
            instance.source = RoleSource.MANUAL
            instance.granted_by = granted_by
            await instance.save()
        return instance

    @staticmethod
    async def remove(user: User, role: Role) -> int:
        tenant_id = _tenant_id_for_role(role)
        return await UserRole.filter(user=user, role=role, tenant_id=tenant_id).delete()

    @staticmethod
    async def list_for_user(user: User) -> List[UserRole]:
        """Roles the user holds in the current tenant (excludes the global
        SUPER_ADMIN row — check ``AuthService.is_super_admin`` for that)."""
        return await UserRole.filter(user=user, tenant_id=current_tenant_id())

    @staticmethod
    async def list_for_user_by_source(user: User, source: RoleSource) -> List[UserRole]:
        return await UserRole.filter(
            user=user, source=source, tenant_id=current_tenant_id()
        )

    @staticmethod
    async def list_users_with_role(role: Role) -> List[User]:
        rows = await UserRole.filter(
            role=role, tenant_id=_tenant_id_for_role(role)
        ).prefetch_related('user')
        return [r.user for r in rows]
