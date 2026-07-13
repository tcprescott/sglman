"""
Discord Service - Business Logic Layer

Handles Discord-related operations like sending DMs.
"""

import logging
from typing import Awaitable, Callable, Tuple, Optional, List, Dict, Set, Union
import discord
from discord.ext import commands

from application.events import dispatch_queue as event_dispatch_queue
from application.services.web_push_service import WebPushService

logger = logging.getLogger(__name__)


def _mirror_dm_to_web_push(user_id: int, message: str) -> None:
    """Fan every outgoing DM out to the recipient's web-push devices.

    send_dm is the chokepoint all notification paths flow through, so mirroring
    here gives device notifications the exact coverage DMs have. The mirror is
    enqueued fire-and-forget onto the event dispatch worker — the caller may be
    the serial discord_queue worker or a UI click handler awaiting send_dm
    inline, and neither may ever wait on push-service round-trips. No coroutine
    is created at all while VAPID is unconfigured.
    """
    if not WebPushService.is_configured():
        return
    event_dispatch_queue.enqueue(WebPushService().mirror_dm(user_id, message))


# Shared bot instance (singleton pattern)
_bot_instance: Optional[commands.Bot] = None


# ---------------------------------------------------------------------------
# Interaction-handler and DM view-factory registries
#
# These invert what used to be a bidirectional import cycle between this module
# and the Discord bot package (previously held together by ~20 deferred,
# function-body imports). The bot package registers each interaction handler
# and view factory here at startup, so the dependency now runs one way (the bot
# package -> ``application.services``) and this module never imports it back.
# Mirrors ``application/match_events.py``.
# See docs/reviews/2026-07-project-structure-review.md, roadmap item 21.
# ---------------------------------------------------------------------------

# Stable view-factory kinds, shared with the bot package's registration so the
# DM senders below and the registering code agree on the lookup keys.
VIEW_CREW_SIGNUP = 'crew_signup'
VIEW_MATCH_ACK = 'match_ack'
VIEW_CREW_ACK = 'crew_ack'
VIEW_VOLUNTEER_ACK = 'volunteer_ack'
VIEW_UNWATCH = 'match_watch'

InteractionHandler = Callable[[discord.Interaction], Awaitable[None]]
ViewFactory = Callable[..., discord.ui.View]

_interaction_handlers: Dict[str, InteractionHandler] = {}
_view_factories: Dict[str, ViewFactory] = {}


def register_interaction_handler(prefix: str, handler: InteractionHandler) -> None:
    """Register a component-interaction handler keyed by its custom_id prefix.

    ``on_interaction`` dispatches an incoming component interaction to the
    handler whose ``prefix`` matches the text before the first ``:`` in the
    button's ``custom_id``.
    """
    _interaction_handlers[prefix] = handler


def register_view_factory(kind: str, factory: ViewFactory) -> None:
    """Register a Discord ``View`` factory keyed by ``kind`` (a ``VIEW_*`` const).

    The DM senders look the factory up by ``kind`` instead of importing it from
    the bot package directly.
    """
    _view_factories[kind] = factory


async def _sync_member_roles(guild_id: int, discord_user_id: int) -> None:
    """Re-sync a member's app roles when their Discord roles change.

    Runs in the bot event loop on ``GUILD_MEMBER_UPDATE`` / member-remove
    events. Lazily imports services to avoid a circular import with
    ``discord_role_mapping_service``. Best-effort: logs and swallows so a bad
    event can never crash the gateway connection.
    """
    try:
        from application.services.tenant_service import TenantService
        from application.services.discord_role_mapping_service import DiscordRoleMappingService
        from models import User

        # A guild may back several tenants (a shared server), so sync every one.
        # Unknown guild (linked to no tenant) -> empty list -> nothing to do. Each
        # per-tenant sync wraps its own tenant_scope and never raises.
        tenants = await TenantService.list_tenants_for_guild(guild_id)
        if not tenants:
            return
        user = await User.get_or_none(discord_id=discord_user_id)
        if user is None:
            return
        service = DiscordRoleMappingService()
        for tenant in tenants:
            await service.sync_user_roles_for_tenant(user, tenant)
    except Exception:
        logger.exception('Live role sync failed for discord_id=%s', discord_user_id)


def get_discord_bot() -> commands.Bot:
    """
    Get or create the shared Discord bot instance.
    
    Returns:
        The Discord bot instance
    """
    global _bot_instance # type: ignore
    if _bot_instance is None:
        # Intents required for DM, guild/role visibility
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.dm_messages = True
        
        _bot_instance = commands.Bot(command_prefix='!', intents=intents)
        
        @_bot_instance.event
        async def on_ready() -> None:
            print(f'Discord bot ready. Logged in as {_bot_instance.user}')

        @_bot_instance.event
        async def on_interaction(interaction: discord.Interaction) -> None:
            if interaction.type == discord.InteractionType.component:
                custom_id = (interaction.data or {}).get('custom_id', '')
                prefix = custom_id.split(':', 1)[0]
                handler = _interaction_handlers.get(prefix)
                if handler is not None:
                    await handler(interaction)

        @_bot_instance.event
        async def on_member_update(before: discord.Member, after: discord.Member) -> None:
            # Only act when role membership actually changed (the event also
            # fires for nick/avatar/timeout updates).
            if {r.id for r in before.roles} == {r.id for r in after.roles}:
                return
            await _sync_member_roles(after.guild.id, after.id)

        @_bot_instance.event
        async def on_member_remove(member: discord.Member) -> None:
            # Left/kicked/banned: re-sync strips their Discord-sourced roles.
            await _sync_member_roles(member.guild.id, member.id)

    return _bot_instance


class DiscordService:
    """Service for Discord-related operations."""
    
    def __init__(self) -> None:
        self._bot = get_discord_bot()

    async def send_dm(
        self,
        user_id: int,
        message: str,
        view_factory: Optional[Callable[[], discord.ui.View]] = None,
    ) -> Tuple[bool, str]:
        """
        Send a direct message to a Discord user, optionally with attached buttons.

        Args:
            user_id: Discord user ID
            message: Message content to send
            view_factory: Optional zero-arg callable returning the
                ``discord.ui.View`` (buttons) to attach. Called just before the
                message is sent, so it only runs once the bot is ready and the
                user has been fetched.

        Returns:
            Tuple of (success: bool, message: str)
            - If successful: (True, "Message sent successfully.")
            - If failed: (False, error_message)
        """
        # Mirror before the bot-readiness checks so device notifications still
        # go out when the bot is down or the user blocks Discord DMs. Corollary:
        # a (False, ...) return means the *Discord* send failed — subscribed
        # devices may already have been notified, so don't blindly re-send.
        _mirror_dm_to_web_push(user_id, message)
        try:
            if self._bot is None:
                return False, "Discord bot not initialized"

            # Check if bot is ready
            if not self._bot.is_ready():
                return False, "Discord bot is not connected. Please try again in a moment."

            user = await self._bot.fetch_user(user_id)
            if view_factory is not None:
                await user.send(message, view=view_factory())
            else:
                await user.send(message)
            return True, "Message sent successfully."
        except discord.NotFound:
            return False, "User not found"
        except discord.Forbidden:
            return False, "Cannot send DM to this user (DMs may be disabled)"
        except discord.HTTPException as e:
            return False, f"Failed to send message: {str(e)}"
        except Exception as e:
            return False, f"Discord bot error: {str(e)}"

    # The five view-bearing senders below are thin wrappers over send_dm: each
    # resolves its registered view factory by kind (populated by the bot package
    # at startup — see the registries above) and defers to send_dm.
    async def send_dm_with_crew_buttons(self, user_id: int, message: str, match_id: int) -> Tuple[bool, str]:
        """Send a DM with the commentator/tracker crew signup buttons for a match."""
        return await self.send_dm(user_id, message, lambda: _view_factories[VIEW_CREW_SIGNUP](match_id))

    async def send_dm_with_acknowledgment_button(self, user_id: int, message: str, match_id: int) -> Tuple[bool, str]:
        """Send a DM with a match Acknowledge button."""
        return await self.send_dm(user_id, message, lambda: _view_factories[VIEW_MATCH_ACK](match_id))

    async def send_dm_with_crew_acknowledgment_button(
        self,
        user_id: int,
        message: str,
        crew_type: str,
        crew_id: int,
    ) -> Tuple[bool, str]:
        """Send a DM with a crew-assignment Acknowledge button.

        ``crew_type`` is 'commentator' or 'tracker'; ``crew_id`` is the crew row id.
        """
        return await self.send_dm(user_id, message, lambda: _view_factories[VIEW_CREW_ACK](crew_type, crew_id))

    async def send_dm_with_volunteer_acknowledgment_button(
        self,
        user_id: int,
        message: str,
        assignment_id: int,
    ) -> Tuple[bool, str]:
        """Send a DM with a volunteer shift Acknowledge button."""
        return await self.send_dm(user_id, message, lambda: _view_factories[VIEW_VOLUNTEER_ACK](assignment_id))

    async def send_dm_with_unwatch_button(self, user_id: int, message: str, match_id: int) -> Tuple[bool, str]:
        """Send a DM with an Unwatch button for match watchers."""
        return await self.send_dm(user_id, message, lambda: _view_factories[VIEW_UNWATCH](match_id))

    def get_bot(self) -> Optional[commands.Bot]:
        """Get the Discord bot instance."""
        return self._bot

    async def list_guilds(self) -> Tuple[bool, Union[List[Dict[str, Union[int, str]]], str]]:
        """
        Retrieve the list of guilds (servers) the bot is currently connected to.

        Returns:
            Tuple[success, data]
            - On success: (True, [{"id": int, "name": str}, ...])
            - On failure: (False, error_message)
        """
        try:
            if self._bot is None:
                return False, "Discord bot not initialized"

            if not self._bot.is_ready():
                return False, "Discord bot is not connected. Please try again in a moment."

            guilds = self._bot.guilds  # cached list of Guild objects
            data = [{"id": g.id, "name": g.name} for g in guilds]
            return True, data
        except Exception as e:
            return False, f"Failed to retrieve guilds: {str(e)}"

    async def list_guild_roles(self, guild_id: int) -> Tuple[bool, Union[List[Dict[str, Union[int, str]]], str]]:
        """
        Retrieve all roles for a given guild.

        Args:
            guild_id: The Discord guild ID (snowflake)

        Returns:
            Tuple[success, data]
            - On success: (True, [{"id": int, "name": str}, ...])
            - On failure: (False, error_message)
        """
        try:
            if self._bot is None:
                return False, "Discord bot not initialized"

            if not self._bot.is_ready():
                return False, "Discord bot is not connected. Please try again in a moment."

            guild = self._bot.get_guild(guild_id)
            if guild is None:
                # Try fetching from API as a fallback
                try:
                    guild = await self._bot.fetch_guild(guild_id)
                except discord.NotFound:
                    return False, "Guild not found"
                except discord.Forbidden:
                    return False, "Insufficient permissions to access this guild"

            roles_list: List[discord.Role]
            try:
                # Prefer explicit fetch to ensure complete/updated role list
                roles_list = await guild.fetch_roles()  # type: ignore[attr-defined]
            except Exception:
                # Fallback to cached roles if fetch is unavailable or fails
                roles_list = list(getattr(guild, "roles", []))

            data = [{"id": r.id, "name": r.name} for r in roles_list]
            return True, data
        except discord.HTTPException as e:
            return False, f"Discord HTTP error while retrieving roles: {str(e)}"
        except Exception as e:
            return False, f"Failed to retrieve roles: {str(e)}"

    async def _modify_role(
        self, guild_id: int, user_id: int, role_id: int, reason: Optional[str], *, add: bool,
    ) -> Tuple[bool, str]:
        """Add or remove a guild role for a member, depending on ``add``."""
        gerund = "adding" if add else "removing"
        past = "added to" if add else "removed from"
        verb = "add" if add else "remove"
        try:
            if self._bot is None:
                return False, "Discord bot not initialized"
            if not self._bot.is_ready():
                return False, "Discord bot is not connected. Please try again in a moment."

            guild = self._bot.get_guild(guild_id) or await self._bot.fetch_guild(guild_id)
            if guild is None:
                return False, "Guild not found"

            member = guild.get_member(user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.NotFound:
                    return False, "Member not found in guild"

            role = guild.get_role(role_id)
            if role is None:
                # Ensure roles are available; try fetching full list
                try:
                    roles_list = await guild.fetch_roles()  # type: ignore[attr-defined]
                    role = next((r for r in roles_list if r.id == role_id), None)
                except Exception:
                    role = None

            if role is None:
                return False, "Role not found in guild"

            if add:
                await member.add_roles(role, reason=reason)
            else:
                await member.remove_roles(role, reason=reason)
            return True, f"Role {past} user"
        except discord.Forbidden:
            return False, "Bot lacks permissions or role hierarchy prevents this action"
        except discord.HTTPException as e:
            return False, f"Discord HTTP error while {gerund} role: {str(e)}"
        except Exception as e:
            return False, f"Failed to {verb} role: {str(e)}"

    async def add_role_to_user(self, guild_id: int, user_id: int, role_id: int, reason: Optional[str] = None) -> Tuple[bool, str]:
        """
        Add a role to a user in a given guild.

        Args:
            guild_id: Target guild ID
            user_id: Target user ID (member)
            role_id: Role ID to add
            reason: Optional audit log reason

        Returns:
            (success, message)
        """
        return await self._modify_role(guild_id, user_id, role_id, reason, add=True)

    async def remove_role_from_user(self, guild_id: int, user_id: int, role_id: int, reason: Optional[str] = None) -> Tuple[bool, str]:
        """
        Remove a role from a user in a given guild.

        Args:
            guild_id: Target guild ID
            user_id: Target user ID (member)
            role_id: Role ID to remove
            reason: Optional audit log reason

        Returns:
            (success, message)
        """
        return await self._modify_role(guild_id, user_id, role_id, reason, add=False)

    async def get_member_role_ids(self, guild_id: int, user_id: int) -> Tuple[bool, Union[Set[int], str]]:
        """
        Retrieve the set of Discord role IDs a member currently holds in a guild.

        Returns:
            Tuple[success, data]
            - On success: (True, {role_id, ...}); the ``@everyone`` role is excluded.
            - When the user is not a member of the guild: (True, set())
            - On a hard failure (bot not ready, API error): (False, error_message)
        """
        try:
            if self._bot is None:
                return False, "Discord bot not initialized"
            if not self._bot.is_ready():
                return False, "Discord bot is not connected. Please try again in a moment."

            guild = self._bot.get_guild(guild_id) or await self._bot.fetch_guild(guild_id)
            if guild is None:
                return False, "Guild not found"

            member = guild.get_member(user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.NotFound:
                    return True, set()

            # Exclude @everyone, whose role id equals the guild id.
            return True, {r.id for r in member.roles if r.id != guild_id}
        except discord.Forbidden:
            return False, "Bot lacks permissions to read guild members"
        except discord.HTTPException as e:
            return False, f"Discord HTTP error while reading member roles: {str(e)}"
        except Exception as e:
            return False, f"Failed to read member roles: {str(e)}"


class MockDiscordService:
    """Stub Discord service for local development without a real bot.

    Mirrors the public surface of DiscordService. Methods log to stdout and
    return success tuples with shapes matching the real implementation, so
    notification code paths can be exercised end-to-end.
    """

    def __init__(self) -> None:
        self._bot = None

    async def send_dm(
        self,
        user_id: int,
        message: str,
        view_factory: Optional[Callable[[], "discord.ui.View"]] = None,
    ) -> Tuple[bool, str]:
        # Deliberately no web-push mirror: mock mode must have no external side
        # effects (a dev with a prod DB snapshot + prod VAPID keys would push
        # to real users' phones). Real delivery requires the real service.
        print(f"[MOCK Discord DM] -> {user_id}: {message}")
        return True, "Message sent (mock)"

    # Thin wrappers matching DiscordService's public surface; all defer to the
    # single send_dm stub above (the buttons are irrelevant in mock mode).
    async def send_dm_with_crew_buttons(self, user_id: int, message: str, match_id: int) -> Tuple[bool, str]:
        return await self.send_dm(user_id, message)

    async def send_dm_with_acknowledgment_button(self, user_id: int, message: str, match_id: int) -> Tuple[bool, str]:
        return await self.send_dm(user_id, message)

    async def send_dm_with_crew_acknowledgment_button(self, user_id: int, message: str, crew_type: str, crew_id: int) -> Tuple[bool, str]:
        return await self.send_dm(user_id, message)

    async def send_dm_with_volunteer_acknowledgment_button(self, user_id: int, message: str, assignment_id: int) -> Tuple[bool, str]:
        return await self.send_dm(user_id, message)

    async def send_dm_with_unwatch_button(self, user_id: int, message: str, match_id: int) -> Tuple[bool, str]:
        return await self.send_dm(user_id, message)

    def get_bot(self) -> None:
        return None

    async def list_guilds(self) -> Tuple[bool, Union[List[Dict[str, Union[int, str]]], str]]:
        return True, [{"id": 1, "name": "Mock Guild"}]

    async def list_guild_roles(self, guild_id: int) -> Tuple[bool, Union[List[Dict[str, Union[int, str]]], str]]:
        return True, [
            {"id": 1, "name": "Mock Role"},
            {"id": 2, "name": "Mock Admin"},
        ]

    async def add_role_to_user(self, guild_id: int, user_id: int, role_id: int, reason: Optional[str] = None) -> Tuple[bool, str]:
        print(f"[MOCK Discord] add_role guild={guild_id} user={user_id} role={role_id} reason={reason!r}")
        return True, "Role added (mock)"

    async def remove_role_from_user(self, guild_id: int, user_id: int, role_id: int, reason: Optional[str] = None) -> Tuple[bool, str]:
        print(f"[MOCK Discord] remove_role guild={guild_id} user={user_id} role={role_id} reason={reason!r}")
        return True, "Role removed (mock)"

    async def get_member_role_ids(self, guild_id: int, user_id: int) -> Tuple[bool, Union[Set[int], str]]:
        print(f"[MOCK Discord] get_member_role_ids guild={guild_id} user={user_id}")
        return True, set()


from application.utils.mock_discord import is_mock_discord  # noqa: E402

# Stable handle to the real implementation; survives the mock swap below so tests
# can exercise the real error branches regardless of MOCK_DISCORD.
_RealDiscordService = DiscordService

if is_mock_discord():
    DiscordService = MockDiscordService  # type: ignore[misc,assignment]
