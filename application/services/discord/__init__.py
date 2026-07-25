"""Discord-facing services — outbound sends and guild/event synchronization.

``DiscordService`` is the send surface (DMs, embeds, guild lookups, mockable via
``MOCK_DISCORD``); ``discord_queue`` is the single background worker that
serializes those sends so request handlers never block on Discord. The
``discord_event_*`` trio mirrors tournament matches into Discord scheduled
events, and the mapping/link services connect guild roles and accounts to app
identity.
"""

from application.services.discord import discord_event_worker, discord_queue
from application.services.discord.discord_event_reconciler_service import (
    DiscordEventReconcilerService,
)
from application.services.discord.discord_event_sync_service import DiscordEventSyncService
from application.services.discord.discord_link_service import DiscordLinkService
from application.services.discord.discord_role_mapping_service import DiscordRoleMappingService
from application.services.discord.discord_service import DiscordService

__all__ = [
    'DiscordEventReconcilerService',
    'DiscordEventSyncService',
    'DiscordLinkService',
    'DiscordRoleMappingService',
    'DiscordService',
    'discord_event_worker',
    'discord_queue',
]
