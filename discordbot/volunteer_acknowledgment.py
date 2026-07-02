"""
Discord volunteer shift acknowledgment interaction handler and view factory.
"""

import logging

import discord

from application.utils.discord_messages import (
    MSG_NO_ACCOUNT,
    volunteer_ack_confirmation,
)
from discordbot._ack_common import make_acknowledged_view, send_ephemeral


logger = logging.getLogger(__name__)

CUSTOM_ID_PREFIX = 'volunteer_ack'

MSG_UNEXPECTED_ERROR = (
    "Something went wrong acknowledging your shift. Please try again, or "
    "acknowledge it from the website."
)


def make_volunteer_acknowledgment_view(assignment_id: int) -> discord.ui.View:
    """Create a Discord View with an Acknowledge button for a volunteer shift."""
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label='Acknowledge',
        style=discord.ButtonStyle.success,
        custom_id=f'{CUSTOM_ID_PREFIX}:{assignment_id}',
    ))
    return view


async def _send(interaction: discord.Interaction, message: str) -> None:
    await send_ephemeral(interaction, message, log_label=CUSTOM_ID_PREFIX)


async def handle_volunteer_acknowledgment_interaction(interaction: discord.Interaction) -> None:
    """Handle a volunteer_ack button press from a Discord DM.

    custom_id format: 'volunteer_ack:<assignment_id>'
    """
    from application.services import UserService, VolunteerScheduleService

    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        logger.exception("Failed to defer Discord volunteer_ack interaction")

    custom_id = (interaction.data or {}).get('custom_id', '')
    parts = custom_id.split(':')
    if len(parts) != 2:
        await _send(interaction, 'Invalid interaction.')
        return
    try:
        assignment_id = int(parts[1])
    except ValueError:
        await _send(interaction, 'Invalid assignment ID.')
        return

    try:
        user = await UserService().get_user_by_discord_id(str(interaction.user.id))
        if not user:
            await _send(interaction, MSG_NO_ACCOUNT)
            return

        assignment = await VolunteerScheduleService().acknowledge(assignment_id, user)
        position_name = (
            assignment.shift.position.name
            if assignment.shift and assignment.shift.position else 'volunteer'
        )

        try:
            await interaction.message.edit(view=make_acknowledged_view(CUSTOM_ID_PREFIX))
        except Exception:
            logger.warning("Could not disable volunteer_ack button (assignment_id=%s)", assignment_id)

        await _send(interaction, volunteer_ack_confirmation(position_name))
    except ValueError as e:
        await _send(interaction, str(e))
    except Exception:
        logger.exception("Volunteer acknowledgment handler failed (assignment_id=%s)", assignment_id)
        await _send(interaction, MSG_UNEXPECTED_ERROR)
