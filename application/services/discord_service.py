"""
Discord Service - Business Logic Layer

Handles Discord-related operations like sending DMs.
"""

from typing import Tuple, Optional, List, Dict, Set, Union
import discord
from discord.ext import commands


# Shared bot instance (singleton pattern)
_bot_instance: Optional[commands.Bot] = None


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
        async def on_ready():
            print(f'Discord bot ready. Logged in as {_bot_instance.user}')

        @_bot_instance.event
        async def on_interaction(interaction: discord.Interaction):
            if interaction.type == discord.InteractionType.component:
                custom_id = (interaction.data or {}).get('custom_id', '')
                if custom_id.startswith('crew_signup:'):
                    from discordbot.crew_signup import handle_crew_signup_interaction
                    await handle_crew_signup_interaction(interaction)
                elif custom_id.startswith('match_ack:'):
                    from discordbot.match_acknowledgment import handle_match_acknowledgment_interaction
                    await handle_match_acknowledgment_interaction(interaction)
                elif custom_id.startswith('crew_ack:'):
                    from discordbot.crew_acknowledgment import handle_crew_acknowledgment_interaction
                    await handle_crew_acknowledgment_interaction(interaction)
                elif custom_id.startswith('volunteer_ack:'):
                    from discordbot.volunteer_acknowledgment import handle_volunteer_acknowledgment_interaction
                    await handle_volunteer_acknowledgment_interaction(interaction)
                elif custom_id.startswith('match_watch:'):
                    from discordbot.watch_buttons import handle_unwatch_interaction
                    await handle_unwatch_interaction(interaction)

    return _bot_instance


class DiscordService:
    """Service for Discord-related operations."""
    
    def __init__(self):
        self._bot = get_discord_bot()
    
    async def send_dm(self, user_id: int, message: str) -> Tuple[bool, str]:
        """
        Send a direct message to a Discord user.
        
        Args:
            user_id: Discord user ID
            message: Message content to send
            
        Returns:
            Tuple of (success: bool, message: str)
            - If successful: (True, "Message sent successfully.")
            - If failed: (False, error_message)
        """
        try:
            if self._bot is None:
                return False, "Discord bot not initialized"
            
            # Check if bot is ready
            if not self._bot.is_ready():
                return False, "Discord bot is not connected. Please try again in a moment."

            user = await self._bot.fetch_user(user_id)
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
    
    async def send_dm_with_crew_buttons(self, user_id: int, message: str, match_id: int) -> Tuple[bool, str]:
        """
        Send a direct message to a Discord user that includes crew signup buttons.

        Args:
            user_id: Discord user ID
            message: Message content
            match_id: Match ID encoded into button custom_ids

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if self._bot is None:
                return False, "Discord bot not initialized"

            if not self._bot.is_ready():
                return False, "Discord bot is not connected. Please try again in a moment."

            from discordbot.crew_signup import make_crew_signup_view
            user = await self._bot.fetch_user(user_id)
            view = make_crew_signup_view(match_id)
            await user.send(message, view=view)
            return True, "Message sent successfully."
        except discord.NotFound:
            return False, "User not found"
        except discord.Forbidden:
            return False, "Cannot send DM to this user (DMs may be disabled)"
        except discord.HTTPException as e:
            return False, f"Failed to send message: {str(e)}"
        except Exception as e:
            return False, f"Discord bot error: {str(e)}"

    async def send_dm_with_acknowledgment_button(self, user_id: int, message: str, match_id: int) -> Tuple[bool, str]:
        """
        Send a direct message to a Discord user with a match acknowledgment button.

        Args:
            user_id: Discord user ID
            message: Message content
            match_id: Match ID encoded into the button custom_id

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if self._bot is None:
                return False, "Discord bot not initialized"

            if not self._bot.is_ready():
                return False, "Discord bot is not connected. Please try again in a moment."

            from discordbot.match_acknowledgment import make_match_acknowledgment_view
            user = await self._bot.fetch_user(user_id)
            view = make_match_acknowledgment_view(match_id)
            await user.send(message, view=view)
            return True, "Message sent successfully."
        except discord.NotFound:
            return False, "User not found"
        except discord.Forbidden:
            return False, "Cannot send DM to this user (DMs may be disabled)"
        except discord.HTTPException as e:
            return False, f"Failed to send message: {str(e)}"
        except Exception as e:
            return False, f"Discord bot error: {str(e)}"

    async def send_dm_with_crew_acknowledgment_button(
        self,
        user_id: int,
        message: str,
        crew_type: str,
        crew_id: int,
    ) -> Tuple[bool, str]:
        """
        Send a direct message to a Discord user with a crew acknowledgment button.

        Args:
            user_id: Discord user ID
            message: Message content
            crew_type: 'commentator' or 'tracker'
            crew_id: Crew row ID encoded into the button custom_id

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if self._bot is None:
                return False, "Discord bot not initialized"

            if not self._bot.is_ready():
                return False, "Discord bot is not connected. Please try again in a moment."

            from discordbot.crew_acknowledgment import make_crew_acknowledgment_view
            user = await self._bot.fetch_user(user_id)
            view = make_crew_acknowledgment_view(crew_type, crew_id)
            await user.send(message, view=view)
            return True, "Message sent successfully."
        except discord.NotFound:
            return False, "User not found"
        except discord.Forbidden:
            return False, "Cannot send DM to this user (DMs may be disabled)"
        except discord.HTTPException as e:
            return False, f"Failed to send message: {str(e)}"
        except Exception as e:
            return False, f"Discord bot error: {str(e)}"

    async def send_dm_with_volunteer_acknowledgment_button(
        self,
        user_id: int,
        message: str,
        assignment_id: int,
    ) -> Tuple[bool, str]:
        """Send a DM to a Discord user with a volunteer shift acknowledgment button."""
        try:
            if self._bot is None:
                return False, "Discord bot not initialized"

            if not self._bot.is_ready():
                return False, "Discord bot is not connected. Please try again in a moment."

            from discordbot.volunteer_acknowledgment import make_volunteer_acknowledgment_view
            user = await self._bot.fetch_user(user_id)
            view = make_volunteer_acknowledgment_view(assignment_id)
            await user.send(message, view=view)
            return True, "Message sent successfully."
        except discord.NotFound:
            return False, "User not found"
        except discord.Forbidden:
            return False, "Cannot send DM to this user (DMs may be disabled)"
        except discord.HTTPException as e:
            return False, f"Failed to send message: {str(e)}"
        except Exception as e:
            return False, f"Discord bot error: {str(e)}"

    async def send_dm_with_unwatch_button(self, user_id: int, message: str, match_id: int) -> Tuple[bool, str]:
        """
        Send a direct message to a Discord user with an Unwatch button.

        Args:
            user_id: Discord user ID
            message: Message content
            match_id: Match ID encoded into the button custom_id

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if self._bot is None:
                return False, "Discord bot not initialized"

            if not self._bot.is_ready():
                return False, "Discord bot is not connected. Please try again in a moment."

            from discordbot.watch_buttons import make_unwatch_view
            user = await self._bot.fetch_user(user_id)
            view = make_unwatch_view(match_id)
            await user.send(message, view=view)
            return True, "Message sent successfully."
        except discord.NotFound:
            return False, "User not found"
        except discord.Forbidden:
            return False, "Cannot send DM to this user (DMs may be disabled)"
        except discord.HTTPException as e:
            return False, f"Failed to send message: {str(e)}"
        except Exception as e:
            return False, f"Discord bot error: {str(e)}"

    def get_bot(self):
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

    def __init__(self):
        self._bot = None

    async def send_dm(self, user_id: int, message: str) -> Tuple[bool, str]:
        print(f"[MOCK Discord DM] -> {user_id}: {message}")
        return True, "Message sent (mock)"

    async def send_dm_with_crew_buttons(self, user_id: int, message: str, match_id: int) -> Tuple[bool, str]:
        print(f"[MOCK Discord DM] -> {user_id} (match {match_id}, crew buttons): {message}")
        return True, "Message sent (mock)"

    async def send_dm_with_acknowledgment_button(self, user_id: int, message: str, match_id: int) -> Tuple[bool, str]:
        print(f"[MOCK Discord DM] -> {user_id} (match {match_id}, ack button): {message}")
        return True, "Message sent (mock)"

    async def send_dm_with_crew_acknowledgment_button(self, user_id: int, message: str, crew_type: str, crew_id: int) -> Tuple[bool, str]:
        print(f"[MOCK Discord DM] -> {user_id} ({crew_type} {crew_id}, ack button): {message}")
        return True, "Message sent (mock)"

    async def send_dm_with_volunteer_acknowledgment_button(self, user_id: int, message: str, assignment_id: int) -> Tuple[bool, str]:
        print(f"[MOCK Discord DM] -> {user_id} (volunteer assignment {assignment_id}, ack button): {message}")
        return True, "Message sent (mock)"

    async def send_dm_with_unwatch_button(self, user_id: int, message: str, match_id: int) -> Tuple[bool, str]:
        print(f"[MOCK Discord DM] -> {user_id} (match {match_id}, unwatch button): {message}")
        return True, "Message sent (mock)"

    def get_bot(self):
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

if is_mock_discord():
    DiscordService = MockDiscordService  # type: ignore[misc,assignment]
