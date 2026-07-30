"""Tenant Membership Service - Business Logic Layer

Who belongs to a community, and who may change that.

Membership is the **wider set**: every role-holder is a member, not every member
holds a role. That invariant is enforced where roles are written
(``UserService.grant_role``, the Discord role sync) and defended here — removing
a member who still holds roles is refused rather than cascading a revoke.

``TenantMembership`` is exempt from ``check_tenant_scoping`` (cross-tenant by
nature: the row *is* the tenant linkage), so its queries pass tenant ids
explicitly rather than going through ``scoped(...)``.
"""

from typing import List

from application.events import EventType
from application.repositories.tenant_membership_repository import TenantMembershipRepository
from application.repositories.user_repository import UserRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.tenant_context import require_tenant_id
from models import User


class TenantMembershipService:
    """Membership reads and writes for the tenant in scope."""

    def __init__(self):
        self.audit_service = AuditService()

    async def list_members(self) -> List[User]:
        """Everyone who belongs to the tenant in scope, by username."""
        rows = await TenantMembershipRepository.list_for_tenant(require_tenant_id())
        return sorted((m.user for m in rows), key=lambda u: (u.username or '').lower())

    async def addable_users(self) -> List[User]:
        """Accounts that could be added to this community but are not in it yet.

        Deliberately reads the *global* account list: identity is shared across
        communities, so "add an existing person to my community" has to be able
        to see people who are not here yet. That makes it the one person-picker
        that is legitimately platform-wide — which is why it lives here, named
        for what it does, rather than as a bare ``get_all_users()`` call in the
        page.
        """
        members = {u.id for u in await self.list_members()}
        return [
            u for u in await UserRepository.get_all()
            if u.id not in members and not u.is_system
        ]

    async def is_member(self, user: User) -> bool:
        return await TenantMembershipRepository.is_member(user.id, require_tenant_id())

    async def add_member(self, actor: User, user: User) -> None:
        """Put a user in this community. Idempotent."""
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            'Only Staff can manage community membership',
        )
        tenant_id = require_tenant_id()
        if await TenantMembershipRepository.is_member(user.id, tenant_id):
            return
        await TenantMembershipRepository.add(user, tenant_id)
        await self.audit_service.write_and_publish(
            actor, AuditActions.TENANT_MEMBER_ADDED,
            {'target_user_id': user.id},
            EventType.TENANT_MEMBER_ADDED,
        )

    async def remove_member(self, actor: User, user: User) -> None:
        """Take a user out of this community.

        Refuses while they hold any role here: removing the membership would
        break the "a role implies membership" invariant from the other side, and
        silently revoking their roles because staff clicked Remove on a table row
        is exactly the kind of invisible side effect this codebase avoids.
        """
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            'Only Staff can manage community membership',
        )
        held = await AuthService.get_roles(user)
        if held:
            raise ValueError(
                f"{user.display_name or user.username} holds roles in this "
                'community — revoke them before removing the membership.'
            )
        tenant_id = require_tenant_id()
        removed = await TenantMembershipRepository.remove(user.id, tenant_id)
        if not removed:
            raise ValueError('That user is not a member of this community.')
        await self.audit_service.write_and_publish(
            actor, AuditActions.TENANT_MEMBER_REMOVED,
            {'target_user_id': user.id},
            EventType.TENANT_MEMBER_REMOVED,
        )

    @staticmethod
    async def ensure_member(user: User) -> None:
        """Idempotent, unaudited membership for the in-scope tenant.

        The hook for "a role in a tenant implies membership in it": called from a
        role grant that is audited in its own right, so a second audit row would
        only be noise.
        """
        await TenantMembershipRepository.add(user, require_tenant_id())
