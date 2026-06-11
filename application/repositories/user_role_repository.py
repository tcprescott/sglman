"""
UserRole Repository - Data Access Layer

Handles database operations for the userrole join table.
"""

from typing import List, Optional

from models import Role, RoleSource, User, UserRole


class UserRoleRepository:
    """Repository for UserRole data access."""

    @staticmethod
    async def add(
        user: User,
        role: Role,
        granted_by: Optional[User] = None,
        source: RoleSource = RoleSource.MANUAL,
    ) -> UserRole:
        instance, created = await UserRole.get_or_create(
            user=user, role=role,
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
        return await UserRole.filter(user=user, role=role).delete()

    @staticmethod
    async def list_for_user(user: User) -> List[UserRole]:
        return await UserRole.filter(user=user)

    @staticmethod
    async def list_for_user_by_source(user: User, source: RoleSource) -> List[UserRole]:
        return await UserRole.filter(user=user, source=source)

    @staticmethod
    async def list_users_with_role(role: Role) -> List[User]:
        rows = await UserRole.filter(role=role).prefetch_related('user')
        return [r.user for r in rows]
