"""
Discord crew acknowledgment interaction handler and view factory.
"""

import logging

import discord

from application.utils.discord_messages import (
    crew_ack_confirmation,
    MSG_NO_ACCOUNT,
    MSG_UNEXPECTED_ERROR_CREW,
)
from discordbot._ack_common import make_acknowledged_view, send_ephemeral


logger = logging.getLogger(__name__)

CUSTOM_ID_PREFIX = 'crew_ack'


def make_crew_acknowledgment_view(crew_type: str, crew_id: int) -> discord.ui.View:
    """Create a Discord View with an Acknowledge button for a crew assignment."""
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label='Acknowledge',
        style=discord.ButtonStyle.success,
        custom_id=f'{CUSTOM_ID_PREFIX}:{crew_type}:{crew_id}',
    ))
    return view


async def _send(interaction: discord.Interaction, message: str) -> None:
    await send_ephemeral(interaction, message, log_label=CUSTOM_ID_PREFIX)


async def handle_crew_acknowledgment_interaction(interaction: discord.Interaction) -> None:
    """
    Handle a crew_ack button press from a Discord DM.

    custom_id format: 'crew_ack:<crew_type>:<crew_id>'
    Responds ephemerally so only the clicking user sees the result.
    """
    from application.repositories import UserRepository
    from application.services import CrewService

    # Defer immediately to extend Discord's 3-second interaction deadline; the
    # downstream DB work (fetch user, fetch crew, update, audit) can exceed it.
    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        logger.exception("Failed to defer Discord crew_ack interaction")

    custom_id = (interaction.data or {}).get('custom_id', '')
    parts = custom_id.split(':')
    if len(parts) != 3 or parts[1] not in ('commentator', 'tracker'):
        await _send(interaction, 'Invalid interaction.')
        return

    crew_type = parts[1]
    try:
        crew_id = int(parts[2])
    except ValueError:
        await _send(interaction, 'Invalid crew ID.')
        return

    try:
        user = await UserRepository().get_by_discord_id(str(interaction.user.id))
        if not user:
            await _send(interaction, MSG_NO_ACCOUNT)
            return

        crew_member = await CrewService().acknowledge_crew_assignment(crew_id, crew_type, user)
        match_id = crew_member.match_id

        from models import MatchPlayers
        players = await MatchPlayers.filter(match_id=match_id).prefetch_related('user')
        player_names = ', '.join(p.user.preferred_name for p in players) if players else ''

        try:
            await interaction.message.edit(view=make_acknowledged_view(CUSTOM_ID_PREFIX))
        except Exception:
            logger.warning("Could not disable crew_ack button (crew_id=%s)", crew_id)

        await _send(interaction, crew_ack_confirmation(crew_type, player_names))
    except ValueError as e:
        await _send(interaction, str(e))
    except Exception:
        logger.exception("Crew acknowledgment handler failed (crew_id=%s)", crew_id)
        await _send(interaction, MSG_UNEXPECTED_ERROR_CREW)
