"""
Discord crew signup interaction handler and view factory.
"""

import discord


CUSTOM_ID_PREFIX = 'crew_signup'


def make_crew_signup_view(match_id: int) -> discord.ui.View:
    """Create a Discord View with commentator and tracker signup buttons for a match."""
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label='Sign up as Commentator',
        style=discord.ButtonStyle.primary,
        custom_id=f'{CUSTOM_ID_PREFIX}:commentator:{match_id}',
    ))
    view.add_item(discord.ui.Button(
        label='Sign up as Tracker',
        style=discord.ButtonStyle.secondary,
        custom_id=f'{CUSTOM_ID_PREFIX}:tracker:{match_id}',
    ))
    return view


async def handle_crew_signup_interaction(interaction: discord.Interaction) -> None:
    """
    Handle a crew_signup button press from a Discord DM.

    custom_id format: 'crew_signup:<role>:<match_id>'
    Responds ephemerally so only the clicking user sees the result.
    """
    from application.repositories import UserRepository
    from application.services import MatchService

    custom_id = (interaction.data or {}).get('custom_id', '')
    parts = custom_id.split(':')
    if len(parts) != 3:
        await interaction.response.send_message('Invalid interaction.', ephemeral=True)
        return

    _, role, match_id_str = parts
    try:
        match_id = int(match_id_str)
    except ValueError:
        await interaction.response.send_message('Invalid match ID.', ephemeral=True)
        return

    if role not in ('commentator', 'tracker'):
        await interaction.response.send_message('Invalid role.', ephemeral=True)
        return

    user = await UserRepository().get_by_discord_id(str(interaction.user.id))
    if not user:
        await interaction.response.send_message(
            'You do not have an SGLMan account. Please log in at the website first.',
            ephemeral=True,
        )
        return

    match_service = MatchService()
    match = await match_service.repository.get_by_id(match_id, prefetch_relations=False)
    if not match:
        await interaction.response.send_message('Match not found.', ephemeral=True)
        return

    if match.finished_at is not None:
        await interaction.response.send_message(
            'This match has already finished. Crew signup is closed.',
            ephemeral=True,
        )
        return

    try:
        await match_service.signup_crew(match_id, user, role)
        await interaction.response.send_message(
            f'You have been signed up as a **{role}** for Match ID {match_id}. Awaiting admin approval.',
            ephemeral=True,
        )
    except ValueError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
