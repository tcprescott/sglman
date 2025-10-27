import os

from application.services.discord_service import get_discord_bot, DiscordService

# Get bot token from environment variable
TOKEN = os.getenv('DISCORD_TOKEN')

# Get the shared Discord bot instance
bot = get_discord_bot()

# Initialize Discord service
discord_service = DiscordService()

# Legacy function for backward compatibility - use DiscordService.send_dm() instead
async def send_dm(user_id: int, message: str) -> tuple[bool, str]:
    """
    Send a DM to a user by their Discord ID.
    
    DEPRECATED: Use DiscordService.send_dm() instead.
    This function is kept for backward compatibility.
    """
    return await discord_service.send_dm(user_id, message)

if __name__ == '__main__':
    if not TOKEN:
        print('DISCORD_BOT_TOKEN environment variable not set.')
    else:
        bot.run(TOKEN)
