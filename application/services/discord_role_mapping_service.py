"""
DiscordRoleMapping Service - Business Logic Layer

Manages the mapping of Discord guild roles to application roles and performs
the login-time sync that grants/revokes app roles from a user's Discord roles.
"""

import asyncio
import logging
from typing import List, Set

from application.errors import require_found
from application.repositories.discord_role_mapping_repository import DiscordRoleMappingRepository
from application.repositories.user_repository import UserRepository
from application.repositories.user_role_repository import UserRoleRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.discord_service import DiscordService
from application.services.tenant_service import TenantService
from application.tenant_context import tenant_scope
from models import DiscordRoleMapping, Role, RoleSource, Tenant, User

logger = logging.getLogger(__name__)


class DiscordRoleMappingService:
    """Service for Discord-role-to-app-role mappings and login-time sync."""

    def __init__(self) -> None:
        self.mapping_repository = DiscordRoleMappingRepository()
        self.role_repository = UserRoleRepository()
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
        app_role: Role,
        actor: User,
    ) -> DiscordRoleMapping:
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            "Only Staff can manage Discord role mappings",
        )
        existing = await self.mapping_repository.get_match(guild_id, discord_role_id, app_role)
        if existing is not None:
            raise ValueError("That Discord role is already mapped to this app role")
        mapping = await self.mapping_repository.create(
            guild_id, discord_role_id, discord_role_name, app_role
        )
        await self.audit_service.write_log(
            actor,
            AuditActions.DISCORD_ROLE_MAPPING_ADDED,
            {
                'guild_id': guild_id,
                'discord_role_id': discord_role_id,
                'discord_role_name': discord_role_name,
                'app_role': app_role.value,
            },
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
            'app_role': mapping.app_role.value,
        }
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
            summary['granted'] += len(result.get('granted') or [])
            summary['revoked'] += len(result.get('revoked') or [])
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
        summary: dict = {'granted': [], 'revoked': [], 'skipped': None}
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
                summary['granted'] += result.get('granted') or []
                summary['revoked'] += result.get('revoked') or []
                if result.get('skipped'):
                    skips.add(result['skipped'])
            if not summary['granted'] and not summary['revoked'] and skips:
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
        summary: dict = {'granted': [], 'revoked': [], 'skipped': None}
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
                desired: Set[Role] = {
                    m.app_role for m in mappings if m.discord_role_id in member_role_ids
                }
                current_all = await AuthService.get_roles(user)
                discord_rows = await self.role_repository.list_for_user_by_source(
                    user, RoleSource.DISCORD
                )
                current_discord = {r.role for r in discord_rows}

                for role in desired - current_all:
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

            return summary
        except Exception:
            logger.exception(
                'Unexpected error during Discord role sync for user %s in tenant %s',
                getattr(user, 'id', None), getattr(tenant, 'id', None),
            )
            summary['skipped'] = 'error'
            return summary
