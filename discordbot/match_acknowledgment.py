"""
Discord match acknowledgment interaction handler and view factory.
"""

import logging

import discord

from application.utils.discord_messages import (
    match_ack_confirmation,
    MSG_NO_ACCOUNT,
    MSG_UNEXPECTED_ERROR_MATCH,
)
from discordbot._ack_common import make_acknowledged_view, send_ephemeral


logger = logging.getLogger(__name__)

CUSTOM_ID_PREFIX = 'match_ack'


def make_match_acknowledgment_view(match_id: int) -> discord.ui.View:
    """Create a Discord View with an Acknowledge button for a match."""
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label='Acknowledge',
        style=discord.ButtonStyle.success,
        custom_id=f'{CUSTOM_ID_PREFIX}:ack:{match_id}',
    ))
    return view


async def _send(interaction: discord.Interaction, message: str) -> None:
    await send_ephemeral(interaction, message, log_label=CUSTOM_ID_PREFIX)


async def handle_match_acknowledgment_interaction(interaction: discord.Interaction) -> None:
    """
    Handle a match_ack button press from a Discord DM.

    custom_id format: 'match_ack:ack:<match_id>'
    Responds ephemerally so only the clicking user sees the result.
    """
    from application.repositories import UserRepository
    from application.services import MatchService

    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        logger.exception("Failed to defer Discord match_ack interaction")

    custom_id = (interaction.data or {}).get('custom_id', '')
    parts = custom_id.split(':')
    if len(parts) != 3 or parts[1] != 'ack':
        await _send(interaction, 'Invalid interaction.')
        return

    try:
        match_id = int(parts[2])
    except ValueError:
        await _send(interaction, 'Invalid match ID.')
        return

    try:
        user = await UserRepository().get_by_discord_id(str(interaction.user.id))
        if not user:
            await _send(interaction, MSG_NO_ACCOUNT)
            return

        await MatchService().acknowledge_match(match_id, user)

        from models import MatchPlayers
        players = await MatchPlayers.filter(match_id=match_id).prefetch_related('user')
        player_names = ', '.join(p.user.preferred_name for p in players) if players else ''

        try:
            await interaction.message.edit(view=make_acknowledged_view(CUSTOM_ID_PREFIX))
        except Exception:
            logger.warning("Could not disable match_ack button (match_id=%s)", match_id)

        await _send(interaction, match_ack_confirmation(player_names))
    except ValueError as e:
        await _send(interaction, str(e))
    except Exception:
        logger.exception("Match acknowledgment handler failed (match_id=%s)", match_id)
        await _send(interaction, MSG_UNEXPECTED_ERROR_MATCH)
