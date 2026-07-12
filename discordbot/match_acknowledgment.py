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
    from application.services import MatchService, UserService
    from application.tenant_context import tenant_scope
    from discordbot._tenant import match_tenant_id

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
        # DM buttons carry no tenant; discover it from the match, then scope.
        tenant_id = await match_tenant_id(match_id)
        if tenant_id is None:
            await _send(interaction, 'Match not found.')
            return

        with tenant_scope(tenant_id):
            user = await UserService().get_user_by_discord_id(str(interaction.user.id))
            if not user:
                await _send(interaction, MSG_NO_ACCOUNT)
                return

            match_service = MatchService()
            await match_service.acknowledge_match(match_id, user)

            player_names = await match_service.get_player_names(match_id)

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
