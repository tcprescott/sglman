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

from typing import List, Optional

from application.errors import NotFoundError
from application.events import EventType
from application.repositories.tenant_join_request_repository import TenantJoinRequestRepository
from application.repositories.tenant_membership_repository import TenantMembershipRepository
from application.repositories.user_repository import UserRepository
from application.repositories.user_role_repository import UserRoleRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.tenant_context import require_tenant_id, tenant_scope
from application.utils.discord_embeds import (
    COLOR_CANCELLED,
    COLOR_JOIN_REQUEST,
    notification_embed,
)
from application.utils.discord_messages import join_decided_dm, join_requested_dm
from application.utils.timezone import now_eastern
from models import JoinRequestStatus, Role, TenantJoinRequest, User


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

    # ---- the door: requests to join --------------------------------------

    async def request_to_join(
        self, user: User, tenant_id: int, message: Optional[str] = None,
    ) -> TenantJoinRequest:
        """Ask to join a community you are not in.

        Takes an explicit ``tenant_id``: this is called from a page the
        requester is *not yet a member of*, so it must not depend on anything
        membership-scoped.
        """
        if await TenantMembershipRepository.is_member(user.id, tenant_id):
            raise ValueError('You are already a member of this community.')
        text = (message or '').strip() or None
        if text and len(text) > 500:
            raise ValueError('Keep the message under 500 characters.')

        request = await TenantJoinRequestRepository.upsert_pending(user, tenant_id, text)
        # The requester acts on their own behalf, and the row belongs to the
        # *target* tenant — which they are not scoped to, hence the explicit
        # scope, exactly as bootstrap_staff does.
        with tenant_scope(tenant_id):
            await self.audit_service.write_and_publish(
                user, AuditActions.TENANT_JOIN_REQUESTED,
                {'target_user_id': user.id, 'request_id': request.id},
                EventType.TENANT_JOIN_REQUESTED,
            )
            await self._notify_staff_of_request(user, tenant_id, text)
        return request

    async def get_request(self, user: User, tenant_id: int) -> Optional[TenantJoinRequest]:
        """This user's request in a named tenant, if any.

        Explicit ``tenant_id`` for the same reason ``request_to_join`` takes one:
        the caller is a page the user is not a member of.
        """
        return await TenantJoinRequestRepository.get(user.id, tenant_id)

    async def list_pending(self) -> List[TenantJoinRequest]:
        """Pending requests for the tenant in scope — the staff queue."""
        return await TenantJoinRequestRepository.list_pending(require_tenant_id())

    async def approve_request(self, actor: User, request_id: int) -> TenantJoinRequest:
        request = await self._decidable(actor, request_id)
        await TenantMembershipRepository.add(request.user, request.tenant_id)
        await TenantJoinRequestRepository.decide(
            request, JoinRequestStatus.APPROVED, actor, now_eastern(),
        )
        await self.audit_service.write_and_publish(
            actor, AuditActions.TENANT_JOIN_APPROVED,
            {'target_user_id': request.user_id, 'request_id': request.id},
            EventType.TENANT_JOIN_APPROVED,
        )
        await self._notify_requester(request.user, approved=True)
        return request

    async def deny_request(self, actor: User, request_id: int) -> TenantJoinRequest:
        request = await self._decidable(actor, request_id)
        await TenantJoinRequestRepository.decide(
            request, JoinRequestStatus.DENIED, actor, now_eastern(),
        )
        await self.audit_service.write_and_publish(
            actor, AuditActions.TENANT_JOIN_DENIED,
            {'target_user_id': request.user_id, 'request_id': request.id},
            EventType.TENANT_JOIN_DENIED,
        )
        # Both outcomes, not just the happy one: notification that only fires on
        # success leaves everyone else wondering whether anyone saw it.
        await self._notify_requester(request.user, approved=False)
        return request

    # ---- notification (best-effort; a DM failure never blocks a decision) --

    async def _notify_staff_of_request(
        self, requester: User, tenant_id: int, message: Optional[str],
    ) -> None:
        """DM the community's staff. A request nobody sees is worse than none."""
        from application.services.discord import DiscordService, discord_queue
        from application.services.tenant_service import TenantService

        community = await TenantService.community_name(tenant_id)
        staff = await UserRoleRepository.list_users_with_role(Role.STAFF)
        body = join_requested_dm(
            community, requester.display_name or requester.username, message or '',
        )
        embed = notification_embed(
            title='🚪 Join request',
            color=COLOR_JOIN_REQUEST,
            community_name=community,
            description=body,
        )
        service = DiscordService()
        for member in staff:
            if member.discord_id:
                discord_queue.enqueue(
                    service.send_dm(int(member.discord_id), body, embed=embed)
                )

    async def _notify_requester(self, requester: User, *, approved: bool) -> None:
        from application.services.discord import DiscordService, discord_queue
        from application.services.tenant_service import TenantService

        if not requester.discord_id:
            return
        community = await TenantService.current_community_name()
        body = join_decided_dm(community, approved)
        embed = notification_embed(
            title='🚪 Join request ' + ('approved' if approved else 'declined'),
            color=COLOR_JOIN_REQUEST if approved else COLOR_CANCELLED,
            community_name=community,
            description=body,
        )
        discord_queue.enqueue(
            DiscordService().send_dm(int(requester.discord_id), body, embed=embed)
        )

    async def _decidable(self, actor: User, request_id: int) -> TenantJoinRequest:
        """Load a request this actor may decide, in the tenant in scope."""
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            'Only Staff can decide join requests',
        )
        request = await TenantJoinRequestRepository.get_by_id(request_id)
        # not_found rather than forbidden for another community's request: the
        # message must not confirm that it exists.
        if request is None or request.tenant_id != require_tenant_id():
            raise NotFoundError('That join request no longer exists.')
        if request.status is not JoinRequestStatus.PENDING:
            raise ValueError('That request has already been decided.')
        return request

    @staticmethod
    async def ensure_member(user: User) -> None:
        """Idempotent, unaudited membership for the in-scope tenant.

        The hook for "a role in a tenant implies membership in it": called from a
        role grant that is audited in its own right, so a second audit row would
        only be noise.
        """
        await TenantMembershipRepository.add(user, require_tenant_id())
