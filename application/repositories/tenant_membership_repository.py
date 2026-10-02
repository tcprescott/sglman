"""Tenant Membership Repository.

Ties a global :class:`~models.User` to the :class:`~models.Tenant` rows they
belong to. Queried across tenants (membership is *how* the auth layer decides
whether a user may see a tenant at all), so it is **not** tenant-scoped.
"""

from typing import List, Optional

from models import MembershipSource, TenantMembership, User


class TenantMembershipRepository:
    """Cross-tenant membership lookups + writes."""

    @staticmethod
    async def is_member(user_id: int, tenant_id: int) -> bool:
        return await TenantMembership.exists(user_id=user_id, tenant_id=tenant_id)

    @staticmethod
    async def add(
        user: User, tenant_id: int, source: Optional[MembershipSource] = None,
    ) -> TenantMembership:
        """Idempotent; ``source`` is recorded only when the row is new."""
        membership, _ = await TenantMembership.get_or_create(
            user=user, tenant_id=tenant_id, defaults={'source': source},
        )
        return membership

    @staticmethod
    async def add_returning_created(
        user: User, tenant_id: int, source: Optional[MembershipSource] = None,
    ) -> bool:
        """:meth:`add`, reporting whether the row is new."""
        _membership, created = await TenantMembership.get_or_create(
            user=user, tenant_id=tenant_id, defaults={'source': source},
        )
        return created

    @staticmethod
    async def remove(user_id: int, tenant_id: int) -> int:
        return await TenantMembership.filter(user_id=user_id, tenant_id=tenant_id).delete()

    @staticmethod
    async def list_for_user(user: User) -> List[TenantMembership]:
        return await TenantMembership.filter(user=user).prefetch_related('tenant')

    @staticmethod
    async def list_for_tenant(tenant_id: int) -> List[TenantMembership]:
        return await TenantMembership.filter(tenant_id=tenant_id).prefetch_related('user')
