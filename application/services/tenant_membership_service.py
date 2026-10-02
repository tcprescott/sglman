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

import logging
from datetime import datetime, timedelta, timezone
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
from application.utils.discord_messages_tenant import (
    auto_joined_dm,
    join_decided_dm,
    join_requested_dm,
    member_added_dm,
    member_removed_dm,
)
from models import JoinRequestStatus, Role, TenantJoinRequest, User

logger = logging.getLogger(__name__)

#: How long a declined requester waits before the door takes another request.
#: Without it, request → decline → request again took ten seconds and DM'd
#: every staff member each time.
JOIN_REQUEST_COOLDOWN = timedelta(days=7)


async def _close_pending_request(
    user: User, tenant_id: int, decided_by: Optional[User],
) -> Optional[TenantJoinRequest]:
    """Close ``user``'s pending request here as approved, if they have one.

    For every way into a community other than the queue itself: someone let in
    by Add Member, a role grant or Discord would otherwise sit in the queue,
    where a Decline would tell a member they weren't approved. ``decided_by``
    is the staff member who let them in, or ``None`` when nobody did.
    """
    request = await TenantJoinRequestRepository.get(user.id, tenant_id)
    if request is None or request.status is not JoinRequestStatus.PENDING:
        return None
    await TenantJoinRequestRepository.decide(
        request, JoinRequestStatus.APPROVED, decided_by, datetime.now(timezone.utc),
    )
    return request


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
        closed = await _close_pending_request(user, tenant_id, actor)
        details: dict = {'target_user_id': user.id}
        if closed is not None:
            details['closed_request_id'] = closed.id
        await self.audit_service.write_and_publish(
            actor, AuditActions.TENANT_MEMBER_ADDED, details, EventType.TENANT_MEMBER_ADDED,
        )
        await self._notify_member(user, member_added_dm, by_staff=True)

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
        # Local import: AccommodationService imports this module.
        from application.services.accommodation_service import AccommodationService
        await AccommodationService().close_for_removed_member(actor, user)
        await self._notify_member(user, member_removed_dm)

    # ---- the door: requests to join --------------------------------------

    async def request_to_join(
        self, user: User, tenant_id: int, message: Optional[str] = None,
    ) -> TenantJoinRequest:
        """Ask to join a community you are not in.

        Takes an explicit ``tenant_id``: this is called from a page the
        requester is *not yet a member of*, so it must not depend on anything
        membership-scoped.

        Refused when staff turned ``KEY_JOIN_REQUESTS`` off. The door hides its
        button then, but a page left open from before the switch still has one.
        Requests already pending are untouched: staff can still decide them.
        """
        from application.services.system_config_service import (
            KEY_JOIN_REQUESTS,
            SystemConfigService,
        )

        if await TenantMembershipRepository.is_member(user.id, tenant_id):
            raise ValueError('You are already a member of this community.')
        with tenant_scope(tenant_id):
            if not await SystemConfigService.get_bool(KEY_JOIN_REQUESTS, default=True):
                raise ValueError('This community isn’t taking join requests right now.')
        text = (message or '').strip() or None
        if text and len(text) > 500:
            raise ValueError("That message is a bit long. Keep it under 500 characters.")
        if await self.next_request_allowed_at(user, tenant_id) is not None:
            raise ValueError(
                'Staff declined your last request recently, so you can’t ask again yet.'
            )

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

    async def join_via_discord(self, user: User, tenant_id: int) -> bool:
        """Let a member of the community's linked Discord server straight in.

        The door's alternative to a join request, live only when staff turned on
        ``KEY_DISCORD_AUTO_JOIN`` and the tenant has a guild. True when ``user``
        is a member afterwards. Explicit ``tenant_id`` for the same reason as
        ``request_to_join``.

        Never raises. It runs inside the membership gate on every page a
        non-member opens, and a Discord outage must leave them at the door with
        its Request access button, not on an error page. A bot that cannot say
        whether they are in the server is treated as "not known to be", never as
        yes.
        """
        from application.services.discord import DiscordService
        from application.services.system_config_service import (
            KEY_DISCORD_AUTO_JOIN,
            SystemConfigService,
        )
        from application.services.tenant_service import TenantService

        if user.discord_id is None:
            return False
        try:
            if await TenantMembershipRepository.is_member(user.id, tenant_id):
                return True
            with tenant_scope(tenant_id):
                if not await SystemConfigService.get_bool(KEY_DISCORD_AUTO_JOIN):
                    return False
                tenant = await TenantService.get_by_id(tenant_id)
                if tenant is None or tenant.discord_guild_id is None:
                    return False
                ok, in_guild = await DiscordService().is_guild_member(
                    tenant.discord_guild_id, int(user.discord_id),
                )
                if not ok:
                    logger.warning(
                        'Discord auto-join: guild check failed for tenant %s: %s',
                        tenant_id, in_guild,
                    )
                    return False
                if not in_guild:
                    return False

                await TenantMembershipRepository.add(user, tenant_id)
                # Closed as approved with no decider: nobody on staff decided it.
                # The person learns they're in from the page they're opening
                # (the gate shows a welcome), so no DM to them.
                await _close_pending_request(user, tenant_id, None)
                await self.audit_service.write_and_publish(
                    user, AuditActions.TENANT_MEMBER_ADDED,
                    {'target_user_id': user.id, 'source': 'discord_auto_join'},
                    EventType.TENANT_MEMBER_ADDED,
                )
                await self._notify_staff_of_auto_join(user, tenant_id)
            return True
        except Exception:
            logger.exception(
                'Discord auto-join failed for user %s in tenant %s', user.id, tenant_id,
            )
            return False

    async def get_request(self, user: User, tenant_id: int) -> Optional[TenantJoinRequest]:
        """This user's request in a named tenant, if any.

        Explicit ``tenant_id`` for the same reason ``request_to_join`` takes one:
        the caller is a page the user is not a member of.
        """
        return await TenantJoinRequestRepository.get(user.id, tenant_id)

    async def next_request_allowed_at(self, user: User, tenant_id: int) -> Optional[datetime]:
        """When a recently declined requester may ask again, or ``None`` if now.

        Explicit ``tenant_id``, like :meth:`get_request`: the door asks it.
        """
        request = await TenantJoinRequestRepository.get(user.id, tenant_id)
        if (
            request is None
            or request.status is not JoinRequestStatus.DENIED
            or request.decided_at is None
        ):
            return None
        allowed = request.decided_at + JOIN_REQUEST_COOLDOWN
        return allowed if allowed > datetime.now(timezone.utc) else None

    async def list_pending(self) -> List[TenantJoinRequest]:
        """Pending requests for the tenant in scope — the staff queue."""
        return await TenantJoinRequestRepository.list_pending(require_tenant_id())

    async def approve_request(self, actor: User, request_id: int) -> TenantJoinRequest:
        request = await self._decidable(actor, request_id)
        await TenantMembershipRepository.add(request.user, request.tenant_id)
        await TenantJoinRequestRepository.decide(
            request, JoinRequestStatus.APPROVED, actor, datetime.now(timezone.utc),
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
        # A request left over from before someone was let in another way. A
        # decline would DM a member that they weren't approved.
        if await TenantMembershipRepository.is_member(request.user_id, request.tenant_id):
            raise ValueError(
                f'{request.user.display_name or request.user.username} is already a '
                'member, so there’s nothing to decline. Approve clears the request.'
            )
        await TenantJoinRequestRepository.decide(
            request, JoinRequestStatus.DENIED, actor, datetime.now(timezone.utc),
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
        # "Approve or deny it on the Users tab" was the whole call to action and
        # named a page without linking it; the button is now the tab itself.
        from application.services import notification_links
        link = await notification_links.admin_users()
        service = DiscordService()
        for member in staff:
            if member.discord_id:
                discord_queue.enqueue(
                    service.send_dm(
                        int(member.discord_id), body, embed=embed, link=link,
                    )
                )

    async def _notify_requester(self, requester: User, *, approved: bool) -> None:
        from application.services.discord import DiscordService, discord_queue
        from application.services.tenant_service import TenantService

        if not requester.discord_id:
            return
        community = await TenantService.current_community_name()
        invite = None if approved else await self._invite_link()
        body = join_decided_dm(
            community, approved,
            ask_again_from='' if approved else self._ask_again_markup(),
            has_invite=invite is not None,
        )
        embed = notification_embed(
            title='🚪 Join request ' + ('approved' if approved else 'declined'),
            color=COLOR_JOIN_REQUEST if approved else COLOR_CANCELLED,
            community_name=community,
            description=body,
        )
        # Only the approval gets a button: "you can open the community now" is an
        # invitation, while a decline has nowhere useful to send anyone.
        from application.services import notification_links
        link = await notification_links.community_home() if approved else None
        if invite is not None:
            link = invite
        discord_queue.enqueue(
            DiscordService().send_dm(
                int(requester.discord_id), body, embed=embed, link=link,
            )
        )

    @staticmethod
    def _ask_again_markup() -> str:
        """Discord's date markup for a week from now, so it reads in their zone."""
        when = datetime.now(timezone.utc) + JOIN_REQUEST_COOLDOWN
        return f'<t:{int(when.timestamp())}:D>'

    @staticmethod
    async def _invite_link():
        """The community's Discord invite as a DM button, or ``None``."""
        from application.services.system_config_service import SystemConfigService
        from application.utils.discord_messages import DMLink

        try:
            url = await SystemConfigService.get_discord_invite_url()
        except Exception:
            logger.exception('Join decline: Discord invite lookup failed')
            return None
        return DMLink('Join the Discord server', url) if url else None

    @staticmethod
    async def _notify_member(user: User, build, **kwargs) -> None:
        """DM ``user`` about their own membership, with a link when they're in."""
        from application.services import notification_links
        from application.services.discord import DiscordService, discord_queue
        from application.services.tenant_service import TenantService

        if not user.discord_id:
            return
        try:
            community = await TenantService.current_community_name()
            body = build(community, **kwargs)
            joined = build is not member_removed_dm
            embed = notification_embed(
                title='🚪 Welcome in' if joined else '🚪 Membership removed',
                color=COLOR_JOIN_REQUEST if joined else COLOR_CANCELLED,
                community_name=community,
                description=body,
            )
            link = await notification_links.community_home() if joined else None
            discord_queue.enqueue(
                DiscordService().send_dm(int(user.discord_id), body, embed=embed, link=link)
            )
        except Exception:
            logger.exception('Membership DM to user %s failed', user.id)

    async def _notify_staff_of_auto_join(self, member: User, tenant_id: int) -> None:
        """Tell staff someone walked in through Discord. Best-effort."""
        from application.services import notification_links
        from application.services.discord import DiscordService, discord_queue
        from application.services.tenant_service import TenantService

        try:
            community = await TenantService.community_name(tenant_id)
            body = auto_joined_dm(community, member.display_name or member.username)
            embed = notification_embed(
                title='🚪 New member', color=COLOR_JOIN_REQUEST,
                community_name=community, description=body,
            )
            link = await notification_links.admin_members()
            service = DiscordService()
            for staff in await UserRoleRepository.list_users_with_role(Role.STAFF):
                if staff.discord_id:
                    discord_queue.enqueue(
                        service.send_dm(int(staff.discord_id), body, embed=embed, link=link)
                    )
        except Exception:
            logger.exception('Auto-join staff DM failed for user %s', member.id)

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

        A pending join request is closed when this makes them a member, and
        they're DM'd that they're in, since the door promised a message either
        way. Nobody else is DM'd: the role sync and SpeedGaming import call this
        for people who never asked.
        """
        tenant_id = require_tenant_id()
        if not await TenantMembershipRepository.add_returning_created(user, tenant_id):
            return
        if await _close_pending_request(user, tenant_id, None) is not None:
            await TenantMembershipService._notify_member(user, member_added_dm, by_staff=False)
