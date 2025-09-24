import os
import discord
from discord.ext import commands
from typing import Optional

from theme.tables import user

# Get bot token from environment variable
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Intents required for DM
intents = discord.Intents.default()
intents.members = True
intents.dm_messages = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
	print(f'Bot is ready. Logged in as {bot.user}')

async def send_dm(user_id: int, message: str) -> tuple[bool, str]:
    """Send a DM to a user by their Discord ID."""
    try:
        user = await bot.fetch_user(user_id)
        await user.send(message)
        return True, "Message sent successfully."
    except Exception as e:
        return False, str(e)

if __name__ == '__main__':
	if not TOKEN:
		print('DISCORD_BOT_TOKEN environment variable not set.')
	else:
		bot.run(TOKEN)
