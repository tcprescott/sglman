"""
DiscordRoleMapping Service - Business Logic Layer

Manages the mapping of Discord guild roles to application roles and performs
the login-time sync that grants/revokes app roles from a user's Discord roles.
"""

import asyncio
import logging
from typing import List, Optional, Set, Tuple

from application.errors import require_found
from application.repositories.discord_role_mapping_repository import DiscordRoleMappingRepository
from application.repositories.discord_tournament_grant_repository import (
    DiscordTournamentGrantRepository,
)
from application.repositories.tournament_repository import TournamentRepository
from application.repositories.user_repository import UserRepository
from application.repositories.user_role_repository import UserRoleRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.discord.discord_service import DiscordService
from application.services.tenant_membership_service import TenantMembershipService
from application.services.tenant_service import TenantService
from application.tenant_context import tenant_scope
from models import DiscordRoleMapping, Role, RoleSource, Tenant, TournamentGrant, User

logger = logging.getLogger(__name__)

# Audit vocabulary for a per-tournament grant, keyed by which relation it writes.
# Reuses the actions a staff member's hand-grant already emits so the tournament's
# audit trail reads as one story; ``source`` in the details says who made it.
_GRANT_AUDIT = {
    TournamentGrant.TOURNAMENT_ADMIN: (
        AuditActions.TOURNAMENT_ADMIN_GRANTED, AuditActions.TOURNAMENT_ADMIN_REVOKED,
    ),
    TournamentGrant.CREW_COORDINATOR: (
        AuditActions.TOURNAMENT_CREW_COORDINATOR_GRANTED,
        AuditActions.TOURNAMENT_CREW_COORDINATOR_REVOKED,
    ),
}


class DiscordRoleMappingService:
    """Service for Discord-role-to-app-role mappings and login-time sync."""

    def __init__(self) -> None:
        self.mapping_repository = DiscordRoleMappingRepository()
        self.role_repository = UserRoleRepository()
        self.grant_repository = DiscordTournamentGrantRepository()
        self.tournament_repository = TournamentRepository()
        self.audit_service = AuditService()

    async def list_all_mappings(self) -> List[DiscordRoleMapping]:
        return await self.mapping_repository.get_all()

    async def list_mappings(self, guild_id: int) -> List[DiscordRoleMapping]:
        return await self.mapping_repository.list_for_guild(guild_id)

    async def add_mapping(
        self,
        guild_id: int,
        discord_role_id: int,
        discord_role_name: str,
        actor: User,
        app_role: Optional[Role] = None,
        tournament_grant: Optional[TournamentGrant] = None,
        tournament_id: Optional[int] = None,
    ) -> DiscordRoleMapping:
        """Map a guild role onto either a tenant-wide role or one tournament's grant.

        Exactly one of ``app_role`` / ``tournament_grant`` may be given, and a
        tournament grant must name the tournament it lands on — a guild role is
        guild-wide, so without one there is nothing to scope the grant to.
        """
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            "Only Staff can manage Discord role mappings",
        )
        if (app_role is None) == (tournament_grant is None):
            raise ValueError("Choose either an application role or a tournament grant")

        details = {
            'guild_id': guild_id,
            'discord_role_id': discord_role_id,
            'discord_role_name': discord_role_name,
        }
        if app_role is not None:
            if app_role not in Role.tenant_grantable():
                # The other half of the same door ``UserService.grant_role``
                # closes: a mapping is a *standing* grant, so this one would have
                # handed platform authority to whoever holds a guild role the
                # community's own staff control, on their next login.
                raise ValueError(
                    "Super Admin is a platform role and cannot be mapped from a "
                    "Discord role."
                )
            if tournament_id is not None:
                raise ValueError("An application role applies community-wide, not to one tournament")
            if await self.mapping_repository.get_match(guild_id, discord_role_id, app_role):
                raise ValueError("That Discord role is already mapped to this app role")
            details['app_role'] = app_role.value
        else:
            if tournament_id is None:
                raise ValueError("Pick the tournament this grant applies to")
            tournament = require_found(
                await self.tournament_repository.get_by_id(tournament_id), "Tournament"
            )
            if await self.mapping_repository.get_tournament_match(
                guild_id, discord_role_id, tournament_grant, tournament_id  # type: ignore[arg-type]
            ):
                raise ValueError("That Discord role is already mapped to this tournament grant")
            details['tournament_grant'] = tournament_grant.value  # type: ignore[union-attr]
            details['tournament_id'] = tournament.id

        mapping = await self.mapping_repository.create(
            guild_id, discord_role_id, discord_role_name,
            app_role=app_role, tournament_grant=tournament_grant, tournament_id=tournament_id,
        )
        await self.audit_service.write_log(
            actor, AuditActions.DISCORD_ROLE_MAPPING_ADDED, details,
        )
        return mapping

    async def remove_mapping(self, mapping_id: int, actor: User) -> None:
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            "Only Staff can manage Discord role mappings",
        )
        mapping = require_found(await self.mapping_repository.get_by_id(mapping_id), "Mapping")
        details = {
            'guild_id': mapping.guild_id,
            'discord_role_id': mapping.discord_role_id,
            'discord_role_name': mapping.discord_role_name,
        }
        if mapping.app_role is not None:
            details['app_role'] = mapping.app_role.value
        else:
            details['tournament_grant'] = mapping.tournament_grant.value
            details['tournament_id'] = mapping.tournament_id
        await self.mapping_repository.delete(mapping)
        await self.audit_service.write_log(
            actor, AuditActions.DISCORD_ROLE_MAPPING_REMOVED, details
        )

    async def sync_all_users(self, actor: User) -> dict:
        """Force a Discord-role sync for every user with a Discord account.

        Applies the current mappings immediately instead of waiting for each
        user to next log in. Reuses the defensive per-user ``sync_user_roles``,
        so an unreachable Discord or a single bad user never aborts the run.
        """
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            "Only Staff can sync Discord roles",
        )

        users = await UserRepository.get_all(has_discord=True)
        summary = {
            'users_processed': len(users),
            'granted': 0,
            'revoked': 0,
            'skipped': 0,
        }
        for user in users:
            result = await self.sync_user_roles(user)
            summary['granted'] += (
                len(result.get('granted') or []) + len(result.get('tournament_granted') or [])
            )
            summary['revoked'] += (
                len(result.get('revoked') or []) + len(result.get('tournament_revoked') or [])
            )
            if result.get('skipped'):
                summary['skipped'] += 1

        await self.audit_service.write_log(
            actor, AuditActions.ROLE_DISCORD_SYNC_BULK, dict(summary)
        )
        return summary

    async def sync_user_roles(self, user: User) -> dict:
        """Login-time sync across **every** tenant whose Discord guild this user is in.

        In a multi-tenant deployment a user may belong to several tenants' guilds,
        so login-time sync fans out over all tenants that have a
        ``discord_guild_id`` and syncs each independently (each in its own tenant
        scope). Defensive by design: never raises; a failure in one tenant leaves
        its roles untouched and does not abort the others.
        """
        summary: dict = {
            'granted': [], 'revoked': [],
            'tournament_granted': [], 'tournament_revoked': [],
            'skipped': None,
        }
        try:
            tenants = [t for t in await TenantService.list_tenants() if t.discord_guild_id]
            if not tenants:
                summary['skipped'] = 'no_guild_configured'
                return summary
            # Sync every tenant concurrently: each per-tenant sync is independent
            # (own tenant scope, own Discord call) and never raises, so login
            # latency stays ~one Discord round-trip instead of scaling with the
            # tenant count. asyncio.gather runs each in its own context copy, so
            # the tenant_scope contextvar in one does not leak into another.
            results = await asyncio.gather(*(
                self.sync_user_roles_for_tenant(user, tenant) for tenant in tenants
            ))
            skips: Set[str] = set()
            for result in results:
                for key in ('granted', 'revoked', 'tournament_granted', 'tournament_revoked'):
                    summary[key] += result.get(key) or []
                if result.get('skipped'):
                    skips.add(result['skipped'])
            if not any(
                summary[k] for k in
                ('granted', 'revoked', 'tournament_granted', 'tournament_revoked')
            ) and skips:
                # Surface a single representative skip reason when nothing changed.
                summary['skipped'] = 'discord_unavailable' if 'discord_unavailable' in skips else next(iter(skips))
            return summary
        except Exception:
            logger.exception(
                'Unexpected error during Discord role sync for user %s',
                getattr(user, 'id', None),
            )
            summary['skipped'] = 'error'
            return summary

    async def sync_user_roles_for_tenant(self, user: User, tenant: Tenant) -> dict:
        """Sync a user's Discord-sourced app roles for ONE tenant, scoped to it.

        Uses the tenant's own ``discord_guild_id`` (the routing key) and wraps all
        role reads/writes in ``tenant_scope(tenant.id)`` so grants/revokes land on
        that tenant's ``UserRole`` rows. Never raises (fail-open).
        """
        summary: dict = {
            'granted': [], 'revoked': [],
            'tournament_granted': [], 'tournament_revoked': [],
            'skipped': None,
        }
        guild_id = tenant.discord_guild_id
        if not guild_id:
            summary['skipped'] = 'no_guild_configured'
            return summary
        try:
            ok, payload = await DiscordService().get_member_role_ids(guild_id, user.discord_id)
            if not ok:
                logger.warning('Discord role sync skipped for user %s in tenant %s: %s', user.id, tenant.id, payload)
                summary['skipped'] = 'discord_unavailable'
                return summary
            member_role_ids: Set[int] = payload  # type: ignore[assignment]

            with tenant_scope(tenant.id):
                mappings = await self.mapping_repository.list_for_guild(guild_id)
                # Filtered here as well as at ``add_mapping``, because this side
                # is what a *stored* row reaches. A mapping written before the
                # grantable check existed — or restored from a backup — would
                # otherwise grant platform authority on the next login, silently,
                # with no one performing an action to notice.
                grantable = set(Role.tenant_grantable())
                desired: Set[Role] = {
                    m.app_role for m in mappings
                    if m.app_role in grantable and m.discord_role_id in member_role_ids
                }
                current_all = await AuthService.get_roles(user)
                discord_rows = await self.role_repository.list_for_user_by_source(
                    user, RoleSource.DISCORD
                )
                current_discord = {r.role for r in discord_rows}

                granting = desired - current_all
                if granting:
                    # A role in a tenant implies membership in it. Once per sync,
                    # not once per role — the write is idempotent either way.
                    # Deliberately *before* the grants and inside the existing
                    # try: if it fails, this tenant is skipped and retried on the
                    # next login (fail-open, as the docstring promises), which is
                    # self-healing. Granting first would instead leave roles with
                    # no membership behind — the state wave 4's gate locks out.
                    await TenantMembershipService.ensure_member(user)
                for role in granting:
                    await self.role_repository.add(
                        user, role, granted_by=None, source=RoleSource.DISCORD
                    )
                    await self.audit_service.write_log(
                        user,
                        AuditActions.ROLE_DISCORD_SYNC_GRANTED,
                        {'role': role.value, 'source': RoleSource.DISCORD.value, 'tenant_id': tenant.id},
                    )
                    summary['granted'].append(role.value)

                for role in current_discord - desired:
                    await self.role_repository.remove(user, role)
                    await self.audit_service.write_log(
                        user,
                        AuditActions.ROLE_DISCORD_SYNC_REVOKED,
                        {'role': role.value, 'source': RoleSource.DISCORD.value, 'tenant_id': tenant.id},
                    )
                    summary['revoked'].append(role.value)

                await self._sync_tournament_grants(
                    user, tenant, mappings, member_role_ids, summary
                )

            return summary
        except Exception:
            logger.exception(
                'Unexpected error during Discord role sync for user %s in tenant %s',
                getattr(user, 'id', None), getattr(tenant, 'id', None),
            )
            summary['skipped'] = 'error'
            return summary

    async def _sync_tournament_grants(
        self,
        user: User,
        tenant: Tenant,
        mappings: List[DiscordRoleMapping],
        member_role_ids: Set[int],
        summary: dict,
    ) -> None:
        """Reconcile ``Tournament.admins`` / ``.crew_coordinators`` from the mappings.

        Runs inside the caller's ``tenant_scope``. The revoke half works off
        ``DiscordTournamentGrant`` rows rather than the join tables themselves,
        which is what keeps a staff member's hand-made Tournament Admin safe: no
        provenance row, no revocation.

        A mapping onto an inactive tournament is treated as absent, so ending an
        event takes back the authority its guild role conferred, and re-opening it
        hands that authority back on the next sync.
        """
        desired: Set[Tuple[int, TournamentGrant]] = {
            (m.tournament_id, m.tournament_grant)  # type: ignore[attr-defined]
            for m in mappings
            if m.tournament_grant is not None
            and m.discord_role_id in member_role_ids
            and m.tournament is not None
            and m.tournament.is_active
        }
        recorded = await self.grant_repository.list_for_user(user)
        current: Set[Tuple[int, TournamentGrant]] = {
            (row.tournament_id, row.grant) for row in recorded  # type: ignore[attr-defined]
        }

        for tournament_id, grant in sorted(desired - current):
            # Already held by hand: leave it be rather than recording provenance
            # over it, or a later sync would revoke a grant it never made.
            if await self.tournament_repository.has_tournament_grant(tournament_id, user, grant):
                continue
            tournament = await self.tournament_repository.get_by_id(tournament_id)
            if tournament is None:
                continue
            # Same ordering rationale as the role grants above: membership first,
            # so a failure leaves no grant stranded without one.
            await TenantMembershipService.ensure_member(user)
            await self.tournament_repository.set_tournament_grant(
                tournament, user, grant, granted=True
            )
            await self.grant_repository.add(user, tournament, grant)
            await self.audit_service.write_log(
                user,
                _GRANT_AUDIT[grant][0],
                {
                    'tournament_id': tournament_id, 'target_user_id': user.id,
                    'source': RoleSource.DISCORD.value, 'tenant_id': tenant.id,
                },
            )
            summary['tournament_granted'].append(f'{grant.value}:{tournament_id}')

        for tournament_id, grant in sorted(current - desired):
            tournament = await self.tournament_repository.get_by_id(tournament_id)
            if tournament is not None:
                await self.tournament_repository.set_tournament_grant(
                    tournament, user, grant, granted=False
                )
            await self.grant_repository.remove(user, tournament_id, grant)
            await self.audit_service.write_log(
                user,
                _GRANT_AUDIT[grant][1],
                {
                    'tournament_id': tournament_id, 'target_user_id': user.id,
                    'source': RoleSource.DISCORD.value, 'tenant_id': tenant.id,
                },
            )
            summary['tournament_revoked'].append(f'{grant.value}:{tournament_id}')
