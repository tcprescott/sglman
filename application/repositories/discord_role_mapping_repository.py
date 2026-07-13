"""
DiscordRoleMapping Repository - Data Access Layer

Handles database operations for Discord-role-to-app-role mappings.
"""

from typing import List, Optional

from application.repositories._tenant import current_tenant_id, scoped
from models import DiscordRoleMapping, Role


class DiscordRoleMappingRepository:
    """Repository for DiscordRoleMapping data access.

    A Discord guild may be shared by several tenants, so filtering by ``guild_id``
    does **not** by itself isolate a tenant — every read is tenant-``scoped`` so a
    shared guild's mappings stay separated by community, and by-id access is
    guarded the same way.
    """

    @staticmethod
    async def get_by_id(mapping_id: int) -> Optional[DiscordRoleMapping]:
        return await DiscordRoleMapping.get_or_none(id=mapping_id, tenant_id=current_tenant_id())

    @staticmethod
    async def get_all() -> List[DiscordRoleMapping]:
        return await scoped(DiscordRoleMapping.all()).order_by('discord_role_name', 'app_role')

    @staticmethod
    async def list_for_guild(guild_id: int) -> List[DiscordRoleMapping]:
        return await scoped(DiscordRoleMapping.filter(guild_id=guild_id)).order_by(
            'discord_role_name', 'app_role'
        )

    @staticmethod
    async def get_match(
        guild_id: int, discord_role_id: int, app_role: Role
    ) -> Optional[DiscordRoleMapping]:
        return await DiscordRoleMapping.get_or_none(
            guild_id=guild_id, discord_role_id=discord_role_id, app_role=app_role,
            tenant_id=current_tenant_id(),
        )

    @staticmethod
    async def create(
        guild_id: int,
        discord_role_id: int,
        discord_role_name: str,
        app_role: Role,
    ) -> DiscordRoleMapping:
        return await DiscordRoleMapping.create(
            tenant_id=current_tenant_id(),
            guild_id=guild_id,
            discord_role_id=discord_role_id,
            discord_role_name=discord_role_name,
            app_role=app_role,
        )

    @staticmethod
    async def delete(mapping: DiscordRoleMapping) -> None:
        await mapping.delete()
