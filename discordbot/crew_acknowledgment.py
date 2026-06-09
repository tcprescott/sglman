"""
Discord crew acknowledgment interaction handler and view factory.
"""

import logging

import discord


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


def make_acknowledged_view() -> discord.ui.View:
    """Create a Discord View with a disabled Acknowledged button."""
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label='Acknowledged',
        style=discord.ButtonStyle.secondary,
        custom_id=f'{CUSTOM_ID_PREFIX}:acknowledged',
        disabled=True,
    ))
    return view


async def _send(interaction: discord.Interaction, message: str) -> None:
    """Send a reply via followup if defer succeeded, else fall back to response."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except Exception:
        logger.exception("Failed to send Discord crew_ack response")


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
            await _send(
                interaction,
                'You do not have an SGLMan account. Please log in at the website first.',
            )
            return

        crew_member = await CrewService().acknowledge_crew_assignment(crew_id, crew_type, user)
        match_id = crew_member.match_id

        from models import MatchPlayers
        players = await MatchPlayers.filter(match_id=match_id).prefetch_related('user')
        player_names = ', '.join(p.user.preferred_name for p in players) if players else ''

        try:
            await interaction.message.edit(view=make_acknowledged_view())
        except Exception:
            logger.warning("Could not disable crew_ack button (crew_id=%s)", crew_id)

        confirmation = f'You have acknowledged your {crew_type} assignment for Match ID {match_id}.'
        if player_names:
            confirmation += f' Players: {player_names}.'
        confirmation += ' Thanks!'
        await _send(interaction, confirmation)
    except ValueError as e:
        await _send(interaction, str(e))
    except Exception:
        logger.exception("Crew acknowledgment handler failed (crew_id=%s)", crew_id)
        await _send(
            interaction,
            'An unexpected error occurred. Please try again or use the website to acknowledge.',
        )
