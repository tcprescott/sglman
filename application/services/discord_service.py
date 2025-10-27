"""
Discord Service - Business Logic Layer

Handles Discord-related operations like sending DMs.
"""

from typing import Tuple, Optional
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
    global _bot_instance
    if _bot_instance is None:
        # Intents required for DM
        intents = discord.Intents.default()
        intents.members = True
        intents.dm_messages = True
        
        _bot_instance = commands.Bot(command_prefix='!', intents=intents)
        
        @_bot_instance.event
        async def on_ready():
            print(f'Discord bot ready. Logged in as {_bot_instance.user}')
    
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
            
            user = await self._bot.fetch_user(user_id)
            await user.send(message)
            return True, "Message sent successfully."
        except discord.NotFound:
            return False, "User not found"
        except discord.Forbidden:
            return False, "Cannot send DM to this user (DMs may be disabled)"
        except discord.HTTPException as e:
            return False, f"Failed to send message: {str(e)}"
    
    def get_bot(self):
        """Get the Discord bot instance."""
        return self._bot
