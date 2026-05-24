"""
Discord Service - Business Logic Layer

Handles Discord-related operations like sending DMs.
"""

from typing import Tuple, Optional, List, Dict, Union
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

            await member.add_roles(role, reason=reason)
            return True, "Role added to user"
        except discord.Forbidden:
            return False, "Bot lacks permissions or role hierarchy prevents this action"
        except discord.HTTPException as e:
            return False, f"Discord HTTP error while adding role: {str(e)}"
        except Exception as e:
            return False, f"Failed to add role: {str(e)}"

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
                try:
                    roles_list = await guild.fetch_roles()  # type: ignore[attr-defined]
                    role = next((r for r in roles_list if r.id == role_id), None)
                except Exception:
                    role = None

            if role is None:
                return False, "Role not found in guild"

            await member.remove_roles(role, reason=reason)
            return True, "Role removed from user"
        except discord.Forbidden:
            return False, "Bot lacks permissions or role hierarchy prevents this action"
        except discord.HTTPException as e:
            return False, f"Discord HTTP error while removing role: {str(e)}"
        except Exception as e:
            return False, f"Failed to remove role: {str(e)}"
