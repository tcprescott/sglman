"""
Shared helpers for the Discord acknowledgment interaction handlers
(match_acknowledgment and crew_acknowledgment).
"""

import logging

import discord

logger = logging.getLogger(__name__)


def make_acknowledged_view(prefix: str) -> discord.ui.View:
    """Create a Discord View with a single disabled 'Acknowledged' button."""
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label='Acknowledged',
        style=discord.ButtonStyle.secondary,
        custom_id=f'{prefix}:acknowledged',
        disabled=True,
    ))
    return view


async def send_ephemeral(interaction: discord.Interaction, message: str, *, log_label: str) -> None:
    """Send an ephemeral reply via followup if defer succeeded, else fall back to response."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except Exception:
        logger.exception("Failed to send Discord %s response", log_label)
