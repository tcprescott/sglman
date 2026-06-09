"""
Discord match acknowledgment interaction handler and view factory.
"""

import logging

import discord


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
        logger.exception("Failed to send Discord match_ack response")


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
            await _send(
                interaction,
                'You do not have an SGLMan account. Please log in at the website first.',
            )
            return

        await MatchService().acknowledge_match(match_id, user)

        from models import MatchPlayers
        players = await MatchPlayers.filter(match_id=match_id).prefetch_related('user')
        player_names = ', '.join(p.user.preferred_name for p in players) if players else ''

        try:
            await interaction.message.edit(view=make_acknowledged_view())
        except Exception:
            logger.warning("Could not disable match_ack button (match_id=%s)", match_id)

        confirmation = f'You have acknowledged Match ID {match_id}.'
        if player_names:
            confirmation += f' Players: {player_names}.'
        confirmation += ' Thanks!'
        await _send(interaction, confirmation)
    except ValueError as e:
        await _send(interaction, str(e))
    except Exception:
        logger.exception("Match acknowledgment handler failed (match_id=%s)", match_id)
        await _send(
            interaction,
            'An unexpected error occurred. Please try again or use the website to acknowledge.',
        )
