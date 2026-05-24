"""
Discord match acknowledgment interaction handler and view factory.
"""

import discord


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


async def handle_match_acknowledgment_interaction(interaction: discord.Interaction) -> None:
    """
    Handle a match_ack button press from a Discord DM.

    custom_id format: 'match_ack:ack:<match_id>'
    Responds ephemerally so only the clicking user sees the result.
    """
    from application.repositories import UserRepository
    from application.services import MatchService

    custom_id = (interaction.data or {}).get('custom_id', '')
    parts = custom_id.split(':')
    if len(parts) != 3 or parts[1] != 'ack':
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

    match_service = MatchService()
    try:
        await match_service.acknowledge_match(match_id, user)
        await interaction.response.send_message(
            f'You have acknowledged Match ID {match_id}. Thanks!',
            ephemeral=True,
        )
    except ValueError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
