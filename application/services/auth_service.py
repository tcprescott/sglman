"""
Authorization Service - Business Logic Layer

Stateless policy helpers for role-based access control. All checks accept
a User model (or None). UI code that only has the storage discord_id
should call get_user_from_discord_id() once at page entry to resolve the
User, then pass it into the helpers.
"""

from typing import Any, Optional

from application.tenant_context import get_current_tenant_id
from models import Match, Role, Tournament, User, UserRole


class AuthService:
    """Stateless authorization helpers.

    Role checks are **per tenant**: ``get_roles``/``has_role`` scope every
    ``UserRole`` query to the current tenant, so a STAFF grant in one tenant does
    not carry into another. The one exception is ``SUPER_ADMIN`` — a global
    platform role whose ``UserRole`` row carries ``tenant=NULL``; it is checked
    with :meth:`is_super_admin` (never through the tenant-scoped path) and
    bypasses the admin-view gate.
    """

    # Global roles that grant access to the Admin dashboard. Excludes PROCTOR
    # and VOLUNTEER, whose workflows live on the Volunteer page instead.
    _ADMIN_ROLES = {Role.STAFF, Role.STREAM_MANAGER, Role.EQUIPMENT_MANAGER, Role.VOLUNTEER_COORDINATOR}

    @staticmethod
    def is_system(user: Optional[User]) -> bool:
        """The reserved automation actor (``User.is_system``).

        A field check, not a role query — the system user is trusted
        infrastructure that acts within a ``tenant_scope`` and is authorized for
        automation actions regardless of any granted roles. Gated helpers below
        short-circuit on it so workers/bots never hit a ``PermissionError``.
        """
        return user is not None and getattr(user, 'is_system', False)

    @staticmethod
    async def is_super_admin(user: Optional[User]) -> bool:
        """The global platform role (``UserRole`` with ``tenant=NULL``)."""
        if user is None:
            return False
        return await UserRole.filter(user=user, role=Role.SUPER_ADMIN, tenant=None).exists()

    @staticmethod
    async def get_roles(user: Optional[User]) -> set[Role]:
        """The user's roles **in the current tenant** (excludes SUPER_ADMIN)."""
        if user is None:
            return set()
        tid = get_current_tenant_id()
        if tid is None:
            # No tenant in context (platform surface) — no tenant roles apply.
            return set()
        rows = await UserRole.filter(user=user, tenant_id=tid).values_list('role', flat=True)
        return {Role(r) for r in rows}

    @staticmethod
    async def has_role(user: Optional[User], role: Role) -> bool:
        if user is None:
            return False
        tid = get_current_tenant_id()
        if tid is None:
            return False
        return await UserRole.filter(user=user, role=role, tenant_id=tid).exists()

    @staticmethod
    async def is_staff(user: Optional[User]) -> bool:
        return await AuthService.has_role(user, Role.STAFF)

    @staticmethod
    async def is_proctor(user: Optional[User]) -> bool:
        return await AuthService.has_role(user, Role.PROCTOR)

    @staticmethod
    async def is_stream_manager(user: Optional[User]) -> bool:
        return await AuthService.has_role(user, Role.STREAM_MANAGER)

    @staticmethod
    async def is_triforce_submitter(user: Optional[User]) -> bool:
        return await AuthService.has_role(user, Role.TRIFORCE_SUBMITTER)

    @staticmethod
    async def can_submit_triforce_text(user: Optional[User], tournament: Tournament) -> bool:
        """Submitting requires the paid Triforce Submitter role (staff override),
        and the tournament must be active with a generator that supports texts."""
        from application.services.seedgen_service import SeedGenerationService

        if not tournament.is_active:
            return False
        if not SeedGenerationService.supports_triforce_texts(tournament.seed_generator):
            return False
        return await AuthService.is_staff(user) or await AuthService.is_triforce_submitter(user)

    @staticmethod
    async def is_tournament_admin(user: Optional[User], tournament_id: int) -> bool:
        # PKs are global, so filter by tenant too: a same-id tournament in another
        # tenant must not satisfy the check.
        if user is None:
            return False
        query = Tournament.filter(id=tournament_id, admins__id=user.id)
        tid = get_current_tenant_id()
        if tid is not None:
            query = query.filter(tenant_id=tid)
        return await query.exists()

    @staticmethod
    async def is_crew_coordinator_of(user: Optional[User], tournament_id: int) -> bool:
        if user is None:
            return False
        query = Tournament.filter(id=tournament_id, crew_coordinators__id=user.id)
        tid = get_current_tenant_id()
        if tid is not None:
            query = query.filter(tenant_id=tid)
        return await query.exists()

    @staticmethod
    async def can_view_admin(user: Optional[User]) -> bool:
        """Any admin global role or any TA/CC tournament membership in this
        tenant. A platform SUPER_ADMIN can view any tenant's admin."""
        if user is None:
            return False
        if await AuthService.is_super_admin(user):
            return True
        if await AuthService.get_roles(user) & AuthService._ADMIN_ROLES:
            return True
        # user.admin_tournaments / crew_coordinated_tournaments span tenants (the
        # reverse relation is off the global User) — filter to this tenant.
        tid = get_current_tenant_id()
        admin_q = user.admin_tournaments.all()
        cc_q = user.crew_coordinated_tournaments.all()
        if tid is not None:
            admin_q = admin_q.filter(tenant_id=tid)
            cc_q = cc_q.filter(tenant_id=tid)
        if await admin_q.exists():
            return True
        return await cc_q.exists()

    @staticmethod
    async def can_edit_tournament(user: Optional[User], tournament: Tournament) -> bool:
        if await AuthService.is_staff(user):
            return True
        return await AuthService.is_tournament_admin(user, tournament.id)

    @staticmethod
    async def can_crud_match(user: Optional[User], match: Match) -> bool:
        if await AuthService.is_staff(user):
            return True
        return await AuthService.is_tournament_admin(user, match.tournament_id)

    @staticmethod
    async def can_transition_match(user: Optional[User], match: Match) -> bool:
        """Seat/start/finish/confirm/roll seeds and assign stations."""
        if await AuthService.is_staff(user) or await AuthService.is_proctor(user):
            return True
        return await AuthService.is_tournament_admin(user, match.tournament_id)

    @staticmethod
    async def can_approve_crew(user: Optional[User], match: Match) -> bool:
        if await AuthService.is_staff(user):
            return True
        if await AuthService.is_tournament_admin(user, match.tournament_id):
            return True
        return await AuthService.is_crew_coordinator_of(user, match.tournament_id)

    @staticmethod
    async def can_manage_stream_rooms(user: Optional[User]) -> bool:
        """CRUD on StreamRoom records (the stages themselves)."""
        return await AuthService.is_staff(user) or await AuthService.is_stream_manager(user)

    @staticmethod
    async def is_volunteer_coordinator(user: Optional[User]) -> bool:
        return await AuthService.has_role(user, Role.VOLUNTEER_COORDINATOR)

    @staticmethod
    async def can_manage_volunteers(user: Optional[User]) -> bool:
        """Manage volunteer positions, shifts, and assignments (admin side)."""
        return await AuthService.is_staff(user) or await AuthService.is_volunteer_coordinator(user)

    @staticmethod
    async def is_equipment_manager(user: Optional[User]) -> bool:
        return await AuthService.has_role(user, Role.EQUIPMENT_MANAGER)

    @staticmethod
    async def is_volunteer(user: Optional[User]) -> bool:
        return await AuthService.has_role(user, Role.VOLUNTEER)

    @staticmethod
    async def can_manage_equipment(user: Optional[User]) -> bool:
        """Create/edit/delete lending assets and view private notes/owner."""
        return await AuthService.is_staff(user) or await AuthService.is_equipment_manager(user)

    @staticmethod
    async def can_checkout_equipment(user: Optional[User]) -> bool:
        """Check equipment out (volunteers may only check out to themselves)."""
        if await AuthService.can_manage_equipment(user):
            return True
        return await AuthService.is_volunteer(user)

    @staticmethod
    async def can_checkin_equipment(user: Optional[User]) -> bool:
        """Check equipment back in."""
        return await AuthService.can_manage_equipment(user)

    @staticmethod
    async def can_assign_match_stream(user: Optional[User], match: Match) -> bool:
        """Set a match's stream_room or is_stream_candidate flag.
        Stream Managers can do this globally; TAs can do it for their own tournaments.
        """
        if await AuthService.can_manage_stream_rooms(user):
            return True
        return await AuthService.is_tournament_admin(user, match.tournament_id)

    @staticmethod
    async def _system_admin_staff_or(user: Optional[User], role: Role) -> bool:
        """Shared cascade: system actor, super-admin, staff, or the given role.

        The common ``is_system → is_super_admin → is_staff → has_role`` ladder used
        by the gated ``can_manage_*`` / ``can_admin_*`` helpers.
        """
        if AuthService.is_system(user):
            return True
        if await AuthService.is_super_admin(user):
            return True
        if await AuthService.is_staff(user):
            return True
        return await AuthService.has_role(user, role)

    @staticmethod
    async def can_manage_presets(user: Optional[User]) -> bool:
        """Author/edit the tenant's seed-rolling presets (PR 1+)."""
        return await AuthService._system_admin_staff_or(user, Role.PRESET_MANAGER)

    @staticmethod
    async def can_manage_sync(user: Optional[User]) -> bool:
        """Manage upstream sync config: SpeedGaming links, Discord events, and
        racetime bot/room configuration (PR 3+/7+)."""
        return await AuthService._system_admin_staff_or(user, Role.SYNC_ADMIN)

    @staticmethod
    async def can_admin_qualifier(user: Optional[User], qualifier: Optional[Any] = None) -> bool:
        """Administer async qualifiers (PR 9+).

        Grants to STAFF/super-admin, the global ``QUALIFIER_ADMIN`` role, or — when
        a specific ``qualifier`` is supplied — a per-entity admin listed on its
        ``admins`` M2M. The per-entity path is forward-compatible: the
        ``AsyncQualifier`` model lands in a later PR, so this only dereferences
        ``qualifier.admins`` when a qualifier is actually passed.
        """
        if await AuthService._system_admin_staff_or(user, Role.QUALIFIER_ADMIN):
            return True
        if qualifier is not None and user is not None:
            return await qualifier.admins.filter(id=user.id).exists()
        return False

    @staticmethod
    async def can_grant_roles(user: Optional[User]) -> bool:
        """Grant/revoke UserRole rows and Tournament.admins / crew_coordinators."""
        return await AuthService.is_staff(user)

    @staticmethod
    async def ensure(allowed: bool, message: str = "Permission denied") -> None:
        if not allowed:
            raise PermissionError(message)

    @staticmethod
    async def ensure_super_admin(user: Optional[User]) -> None:
        """Raise ``PermissionError`` unless ``user`` is the global super-admin."""
        await AuthService.ensure(
            await AuthService.is_super_admin(user),
            "Super-admin privileges required",
        )

    @staticmethod
    async def ensure_can_manage_presets(user: Optional[User]) -> None:
        """Raise ``PermissionError`` unless ``user`` may manage seed presets."""
        await AuthService.ensure(
            await AuthService.can_manage_presets(user),
            "You do not have permission to manage presets",
        )

    @staticmethod
    async def ensure_can_manage_sync(user: Optional[User]) -> None:
        """Raise ``PermissionError`` unless ``user`` may manage sync config."""
        await AuthService.ensure(
            await AuthService.can_manage_sync(user),
            "You do not have permission to manage sync configuration",
        )

    @staticmethod
    async def ensure_can_admin_qualifier(
        user: Optional[User], qualifier: Optional[Any] = None
    ) -> None:
        """Raise ``PermissionError`` unless ``user`` may administer qualifiers."""
        await AuthService.ensure(
            await AuthService.can_admin_qualifier(user, qualifier),
            "You do not have permission to administer this qualifier",
        )


async def get_user_from_discord_id(discord_id: str | None) -> Optional[User]:
    """Resolve a discord_id (from app.storage.user) to a User model.

    Returns None when discord_id is absent, the user is no longer in the
    database, or the account has been deactivated (``is_active`` is False) —
    so a deactivated user loses page/role access on their next request, the
    same way the REST API already rejects them.
    Call once at page entry and pass the result into AuthService helpers.
    """
    if not discord_id:
        return None
    user = await User.get_or_none(discord_id=discord_id)
    if user is not None and not user.is_active:
        return None
    return user
