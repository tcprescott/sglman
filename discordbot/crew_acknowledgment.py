"""
Discord crew acknowledgment interaction handler and view factory.
"""

import discord


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


async def handle_crew_acknowledgment_interaction(interaction: discord.Interaction) -> None:
    """
    Handle a crew_ack button press from a Discord DM.

    custom_id format: 'crew_ack:<crew_type>:<crew_id>'
    Responds ephemerally so only the clicking user sees the result.
    """
    from application.repositories import UserRepository
    from application.services import CrewService

    custom_id = (interaction.data or {}).get('custom_id', '')
    parts = custom_id.split(':')
    if len(parts) != 3 or parts[1] not in ('commentator', 'tracker'):
        await interaction.response.send_message('Invalid interaction.', ephemeral=True)
        return

    crew_type = parts[1]
    try:
        crew_id = int(parts[2])
    except ValueError:
        await interaction.response.send_message('Invalid crew ID.', ephemeral=True)
        return

    user = await UserRepository().get_by_discord_id(str(interaction.user.id))
    if not user:
        await interaction.response.send_message(
            'You do not have an SGLMan account. Please log in at the website first.',
            ephemeral=True,
        )
        return

    crew_service = CrewService()
    try:
        crew_member = await crew_service.acknowledge_crew_assignment(crew_id, crew_type, user)
        match_id = crew_member.match_id
        await interaction.response.send_message(
            f'You have acknowledged your {crew_type} assignment for Match ID {match_id}. Thanks!',
            ephemeral=True,
        )
    except ValueError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
