"""
User Service - Business Logic Layer

Coordinates user-related operations and enforces business rules.
"""

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set

from application.repositories.tournament_repository import TournamentRepository
from application.repositories.user_repository import UserRepository
from application.repositories.user_role_repository import UserRoleRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.tenant_membership_service import TenantMembershipService
from application.tenant_context import require_tenant_id
from models import Role, RoleSource, Tournament, TournamentPlayers, User


class UserService:
    """Service for user-related business operations."""

    def __init__(self) -> None:
        self.repository = UserRepository()
        self.role_repository = UserRoleRepository()
        # Enrolment writes go through here rather than straight to the model:
        # the repository is what stamps the tenant on a non-null FK.
        self.tournament_repository = TournamentRepository()
        self.audit_service = AuditService()

    async def get_user_by_discord_id(self, discord_id: str) -> Optional[User]:
        return await self.repository.get_by_discord_id(discord_id)

    async def get_system_user(self) -> User:
        """Resolve the reserved system :class:`User` that automation acts as.

        Workers and bot handlers (racetime, SG ETL, auto-open, qualifier scoring)
        pass the returned row as ``actor`` so audit trails snapshot a real
        username. Idempotent (get-or-create on the sentinel ``discord_id``), so it
        is safe to call before the migration seed has run or in a fresh test DB.
        The row is authorized for automation actions via ``AuthService`` regardless
        of its roles (see :meth:`AuthService.is_system`).
        """
        return await self.repository.get_or_create_system_user()

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        return await self.repository.get_by_id(user_id)

    async def _check_concurrency(
        self,
        user: User,
        check_concurrency: bool,
        initial_updated_at: Optional[datetime],
    ) -> None:
        """Optimistic-concurrency guard for admin edits.

        Raises if the row was modified since the editor loaded it, so a second
        admin's save can't silently clobber the first.
        """
        if not (check_concurrency and initial_updated_at is not None):
            return
        latest_user = await self.repository.get_by_id(user.id)
        if latest_user and latest_user.updated_at != initial_updated_at:
            raise ValueError("This user has been modified by another admin. Please reload and try again.")

    async def get_all_users(
        self,
        role: Optional[Role] = None,
        has_discord: bool = False,
    ) -> List[User]:
        """Every account on the platform.

        Identity is global, so this is a **platform-level** list. Any picker that
        means "people in this community" wants
        :meth:`get_community_people` instead. Two callers are legitimately
        platform-level and both label the widening on screen: the ``/platform``
        first-admin dialog (choosing from every account precisely because the
        target community has no members yet) and the checkout dialog's "Include
        people outside this community" toggle.
        """
        return await self.repository.get_all(role=role, has_discord=has_discord)

    async def get_community_people(
        self,
        *,
        role: Optional[Role] = None,
        has_discord: bool = False,
        include_user_ids: Optional[List[int]] = None,
        include_inactive: bool = False,
    ) -> List[User]:
        """The people of the tenant in scope, for a per-community person picker.

        Named for the concept, not the caller: every per-community picker has
        the same leak and wants the same read. It lives here rather than on
        ``EquipmentService`` deliberately — hanging it there would drag
        ``FeatureFlag.EQUIPMENT``'s declared ``service_modules`` gating onto a
        people query that has nothing to do with equipment.

        This is a **default for a picker, not an authorization rule.** The hard
        rules are enforced by whichever service acts on the choice — see
        ``EquipmentService.checkout`` and the membership check in
        ``CrewService.signup_crew``.

        Raises if there is no tenant in scope: a per-community picker rendered
        outside a tenant is a bug, and that is where it should surface.
        """
        return await self.repository.get_community_people(
            role=role,
            has_discord=has_discord,
            include_user_ids=include_user_ids,
            include_inactive=include_inactive,
        )

    async def get_current_user_from_storage(self, storage_discord_id: Optional[str]) -> Optional[User]:
        if not storage_discord_id:
            return None
        return await self.repository.get_by_discord_id(storage_discord_id)

    async def provision_from_discord_login(
        self,
        discord_id: int,
        username: str,
        avatar: Optional[str] = None,
    ) -> tuple[User, bool]:
        """Get-or-create the ``User`` row for a Discord OAuth login and keep the
        username and avatar hash in sync. Returns ``(user, created)``. An inactive
        account is returned without an identity update so the caller can reject
        the login.

        ``avatar`` is Discord's avatar hash. ``None`` means the caller knows
        nothing about it and the stored hash is left alone; an empty string means
        the account has no custom avatar and clears it.

        A freshly provisioned account writes a ``user.provisioned`` audit entry
        (self-attributed to the new user) so login-time account creation is no
        longer invisible to the audit trail.
        """
        user, created = await self.repository.get_or_create_by_discord_id(
            discord_id, username, avatar,
        )
        if created:
            await self.audit_service.write_log(
                user,
                AuditActions.USER_PROVISIONED,
                {
                    'target_user_id': user.id,
                    'username': username,
                    'discord_id': str(discord_id),
                    'source': 'discord_login',
                },
            )
        elif user.is_active:
            fields: dict = {'username': username}
            if avatar is not None:
                fields['discord_avatar'] = avatar or None
            await self.repository.update(user, **fields)
        return user, created

    async def sync_discord_avatar(
        self, discord_id: int, avatar: Optional[str],
    ) -> bool:
        """Record what Discord currently says a user's avatar hash is.

        The bot's ``on_member_update`` path: a person who never signs in still
        gets a current avatar as long as they share a guild with us. Returns
        ``True`` when the stored hash actually changed. Unknown users are a
        no-op — we do not provision an account off a presence event.
        """
        user = await self.repository.get_by_discord_id(discord_id)
        if user is None:
            return False
        return await self.repository.set_discord_avatar(user, avatar)

    async def create_mock_login_user(
        self,
        discord_id: int,
        username: str,
        display_name: Optional[str] = None,
        role_values: Optional[Iterable[str]] = None,
    ) -> User:
        """Provision a user (and any selected roles) for the MOCK_DISCORD dev
        login flow. This dev-only path performs no permission check (mirroring
        the mock login page it backs) but writes a ``user.provisioned`` audit
        entry so provisioning is audited consistently with the real login path.
        """
        roles = [Role(role_value) for role_value in role_values or []]
        user = await self.repository.create(
            username=username,
            discord_id=discord_id,
            display_name=display_name,
        )
        for role in roles:
            await self.role_repository.add(user, role)
        await self.audit_service.write_log(
            user,
            AuditActions.USER_PROVISIONED,
            {
                'target_user_id': user.id,
                'username': username,
                'discord_id': str(discord_id),
                'source': 'mock_login',
                'roles': [role.value for role in roles],
            },
        )
        return user

    async def get_active_tournaments_categorized(self) -> Dict[str, List[Tournament]]:
        # Ordered by name to match TournamentNotificationService.get_active_tournaments:
        # the profile page renders both lists, and an unordered one reads as a
        # differently-shuffled duplicate of the other.
        tournaments = await Tournament.filter(is_active=True, tenant_id=require_tenant_id()).order_by('name')
        staff_tournaments = [t for t in tournaments if t.staff_administered]
        player_tournaments = [t for t in tournaments if not t.staff_administered]
        return {
            'staff_tournaments': staff_tournaments,
            'player_tournaments': player_tournaments,
            'all_tournaments': tournaments,
        }

    async def get_user_tournament_registrations(self, user: User) -> List[TournamentPlayers]:
        return await TournamentPlayers.filter(user=user, tenant_id=require_tenant_id())

    async def update_user_personal_info(
        self,
        user: User,
        actor: User,
        display_name: Optional[str] = None,
        pronouns: Optional[str] = None,
        dm_notifications: Optional[bool] = None,
    ) -> User:
        """Update the user's own profile fields. Caller is expected to be the
        same user (self-edit); permission check is performed at the page level
        via authentication.
        """
        any_provided = False
        changed: Dict[str, object] = {}
        if display_name is not None:
            any_provided = True
            new_value = display_name.strip() if display_name.strip() else None
            if new_value != user.display_name:
                changed['display_name'] = new_value
            user.display_name = new_value
        if pronouns is not None:
            any_provided = True
            new_value = pronouns.strip() if pronouns.strip() else None
            if new_value != user.pronouns:
                changed['pronouns'] = new_value
            user.pronouns = new_value
        if dm_notifications is not None:
            any_provided = True
            if dm_notifications != user.dm_notifications:
                changed['dm_notifications'] = dm_notifications
            user.dm_notifications = dm_notifications

        if any_provided:
            await user.save()
        if changed:
            await self.audit_service.write_log(
                actor,
                AuditActions.USER_SELF_PROFILE_UPDATED,
                {'target_user_id': user.id, 'changed_fields': changed},
            )
        return user

    async def update_user_tournament_registrations(
        self,
        user: User,
        actor: User,
        selected_tournament_ids: Set[int],
        current_registrations: List[TournamentPlayers],
    ) -> None:
        current_ids = set(tp.tournament_id for tp in current_registrations)
        removed_ids = current_ids - selected_tournament_ids
        added_ids = selected_tournament_ids - current_ids

        for tp in current_registrations:
            if tp.tournament_id in removed_ids:
                await tp.delete()
        created_ids: List[int] = []
        for tournament_id in added_ids:
            tournament = await Tournament.get_or_none(id=tournament_id, tenant_id=require_tenant_id())
            if tournament:
                await self.tournament_repository.enroll_player(tournament, user)
                created_ids.append(tournament_id)

        if created_ids or removed_ids:
            await self.audit_service.write_log(
                actor,
                AuditActions.USER_TOURNAMENT_ENROLLMENT_UPDATED,
                {
                    'target_user_id': user.id,
                    'added_tournament_ids': sorted(created_ids),
                    'removed_tournament_ids': sorted(removed_ids),
                },
            )

    async def create_user(
        self,
        username: str,
        actor: User,
        display_name: Optional[str] = None,
        pronouns: Optional[str] = None,
        is_active: bool = True,
        discord_id: Optional[str] = None,
    ) -> User:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can create users",
        )
        if not username or not username.strip():
            raise ValueError("Enter a username.")
        new_user = await self.repository.create(
            username=username.strip(),
            display_name=display_name.strip() if display_name else None,
            pronouns=pronouns.strip() if pronouns else None,
            is_active=is_active,
            discord_id=discord_id,
        )
        # Staff creating an account from their own admin area mean it for their
        # own community — without this the new user would not appear in the very
        # table they were created from.
        await TenantMembershipService.ensure_member(new_user)
        await self.audit_service.write_log(
            actor,
            AuditActions.USER_CREATED,
            {
                'target_user_id': new_user.id,
                'username': new_user.username,
                'is_active': is_active,
                'discord_id': discord_id,
            },
        )
        return new_user

    async def update_user_profile(
        self,
        user: User,
        actor: User,
        display_name: Optional[str] = None,
        pronouns: Optional[str] = None,
        check_concurrency: bool = False,
        initial_updated_at: Optional[datetime] = None,
    ) -> User:
        """Update display_name / pronouns. Allowed for the user themselves or Staff."""
        if actor.id != user.id and not await AuthService.is_staff(actor):
            raise PermissionError("User cannot edit another user's profile")

        await self._check_concurrency(user, check_concurrency, initial_updated_at)

        update_data = {}
        if display_name is not None:
            update_data['display_name'] = display_name.strip() if display_name else None
        if pronouns is not None:
            update_data['pronouns'] = pronouns.strip() if pronouns else None

        if update_data:
            await self.repository.update(user, **update_data)
            await self.audit_service.write_log(
                actor,
                AuditActions.USER_PROFILE_UPDATED,
                {'target_user_id': user.id, 'changed_fields': update_data},
            )
        return user

    async def update_user_admin_fields(
        self,
        user: User,
        actor: User,
        is_active: Optional[bool] = None,
        check_concurrency: bool = False,
        initial_updated_at: Optional[datetime] = None,
    ) -> User:
        """Update admin-managed user fields (is_active). Staff-only."""
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can edit admin fields",
        )

        await self._check_concurrency(user, check_concurrency, initial_updated_at)

        update_data = {}
        if is_active is not None:
            update_data['is_active'] = is_active

        if update_data:
            previous_is_active = user.is_active
            await self.repository.update(user, **update_data)
            if is_active is not None and is_active != previous_is_active:
                await self.audit_service.write_log(
                    actor,
                    AuditActions.USER_ACTIVATION_CHANGED,
                    {'target_user_id': user.id, 'is_active': is_active},
                )
        return user

    async def grant_role(self, target: User, role: Role, actor: User) -> None:
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            "Only Staff can grant roles",
        )
        await self.role_repository.add(target, role, granted_by=actor, source=RoleSource.MANUAL)
        # A role in a tenant implies membership in it. Guarded on the role rather
        # than on the ambient tenant: grant_role runs *inside* a tenant context,
        # so without this a super-admin grant would make them a member of
        # whichever community happened to grant it.
        if role is not Role.SUPER_ADMIN:
            await TenantMembershipService.ensure_member(target)
        await self.audit_service.write_log(
            actor,
            AuditActions.USER_ROLE_GRANTED,
            {'role': role.value, 'target_user_id': target.id},
        )

    async def revoke_role(self, target: User, role: Role, actor: User) -> None:
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            "Only Staff can revoke roles",
        )
        await self.role_repository.remove(target, role)
        await self.audit_service.write_log(
            actor,
            AuditActions.USER_ROLE_REVOKED,
            {'role': role.value, 'target_user_id': target.id},
        )

    async def manage_tournament_enrollments(
        self,
        user: User,
        actor: User,
        tournament_ids: Set[int],
        is_update: bool = True,
    ) -> None:
        if is_update:
            current_registrations = await self.get_user_tournament_registrations(user)
            await self.update_user_tournament_registrations(
                user, actor, tournament_ids, current_registrations,
            )
        else:
            added: List[int] = []
            for tournament_id in tournament_ids:
                tournament = await Tournament.get_or_none(id=tournament_id, tenant_id=require_tenant_id())
                if tournament:
                    await self.tournament_repository.enroll_player(tournament, user)
                    added.append(tournament_id)
            if added:
                await self.audit_service.write_log(
                    actor,
                    AuditActions.USER_TOURNAMENT_ENROLLMENT_UPDATED,
                    {
                        'target_user_id': user.id,
                        'added_tournament_ids': sorted(added),
                        'removed_tournament_ids': [],
                    },
                )
