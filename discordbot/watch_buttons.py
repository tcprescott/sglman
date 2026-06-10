"""
Discord unwatch interaction handler and view factory.

Renders an Unwatch button on lifecycle DMs sent to match watchers so they
can opt out of further notifications without leaving Discord.
"""

import discord

from application.utils.discord_messages import unwatch_confirmation


CUSTOM_ID_PREFIX = 'match_watch'


def make_unwatch_view(match_id: int) -> discord.ui.View:
    """Create a Discord View with an Unwatch button for a match."""
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label='Unwatch',
        style=discord.ButtonStyle.danger,
        custom_id=f'{CUSTOM_ID_PREFIX}:unwatch:{match_id}',
    ))
    return view


async def handle_unwatch_interaction(interaction: discord.Interaction) -> None:
    """
    Handle an Unwatch button press from a Discord DM.

    custom_id format: 'match_watch:unwatch:<match_id>'
    Responds ephemerally so only the clicking user sees the result.
    """
    from application.repositories import UserRepository
    from application.services import MatchWatcherService

    custom_id = (interaction.data or {}).get('custom_id', '')
    parts = custom_id.split(':')
    if len(parts) != 3 or parts[1] != 'unwatch':
        await interaction.response.send_message('Invalid interaction.', ephemeral=True)
        return

    try:
        match_id = int(parts[2])
    except ValueError:
        await interaction.response.send_message('Invalid match ID.', ephemeral=True)
        return

    user = await UserRepository().get_by_discord_id(str(interaction.user.id))
    if not user:
        await interaction.response.send_message(
            'You do not have an SGLMan account. Please log in at the website first.',
            ephemeral=True,
        )
        return

    try:
        removed = await MatchWatcherService().unwatch(match_id, user)
    except ValueError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return

    from models import MatchPlayers
    players = await MatchPlayers.filter(match_id=match_id).prefetch_related('user')
    player_names = ', '.join(p.user.preferred_name for p in players) if players else ''

    await interaction.response.send_message(
        unwatch_confirmation(player_names, was_watching=removed),
        ephemeral=True,
    )
