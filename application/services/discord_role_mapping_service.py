"""
DiscordRoleMapping Service - Business Logic Layer

Manages the mapping of Discord guild roles to application roles and performs
the login-time sync that grants/revokes app roles from a user's Discord roles.
"""

import logging
from typing import List, Set

from application.repositories.discord_role_mapping_repository import DiscordRoleMappingRepository
from application.repositories.user_role_repository import UserRoleRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.discord_service import DiscordService
from application.services.system_config_service import SystemConfigService
from models import DiscordRoleMapping, Role, RoleSource, User

logger = logging.getLogger(__name__)


class DiscordRoleMappingService:
    """Service for Discord-role-to-app-role mappings and login-time sync."""

    def __init__(self):
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
        mapping = await self.mapping_repository.get_by_id(mapping_id)
        if mapping is None:
            raise ValueError("Mapping not found")
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

    async def sync_user_roles(self, user: User) -> dict:
        """Full-sync a user's Discord-sourced app roles from their guild roles.

        Defensive by design: never raises. On any infrastructure failure it
        leaves existing roles untouched (fail-open) so login is never blocked.
        Manually-granted roles (``source=manual``) are never auto-revoked.
        """
        summary: dict = {'granted': [], 'revoked': [], 'skipped': None}
        try:
            guild_id = await SystemConfigService.get_discord_sync_guild_id()
            if not guild_id:
                summary['skipped'] = 'no_guild_configured'
                return summary

            ok, payload = await DiscordService().get_member_role_ids(guild_id, user.discord_id)
            if not ok:
                # Fail-open: keep existing roles when Discord is unavailable.
                logger.warning('Discord role sync skipped for user %s: %s', user.id, payload)
                summary['skipped'] = 'discord_unavailable'
                return summary
            member_role_ids: Set[int] = payload  # type: ignore[assignment]

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
                    {'role': role.value, 'source': RoleSource.DISCORD.value},
                )
                summary['granted'].append(role.value)

            for role in current_discord - desired:
                await self.role_repository.remove(user, role)
                await self.audit_service.write_log(
                    user,
                    AuditActions.ROLE_DISCORD_SYNC_REVOKED,
                    {'role': role.value, 'source': RoleSource.DISCORD.value},
                )
                summary['revoked'].append(role.value)

            return summary
        except Exception:
            logger.exception(
                'Unexpected error during Discord role sync for user %s',
                getattr(user, 'id', None),
            )
            summary['skipped'] = 'error'
            return summary
