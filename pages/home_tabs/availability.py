"""Home availability section (self-service for any logged-in player)."""

from nicegui import app

from application.services import get_user_from_discord_id
from application.services.player_availability_service import PlayerAvailabilityService
from theme.availability_editor import BLOCK_MODE, render_availability_editor
from theme.section import section_panel


async def availability_tab() -> None:
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    panel = await section_panel(
        "When you can't play",
        icon='schedule',
        subtitle='You count as available for the whole event until you block a time out.',
        help_topics=['player-availability'],
        user=user,
    )
    with panel.body:
        # ``title=''``: the panel above is the heading, and the editor's own
        # ``help_snippet`` icon would duplicate the one in the panel header.
        await render_availability_editor(
            PlayerAvailabilityService(),
            help_text='Block out the times you cannot play; leave the rest alone.',
            title='',
            mode=BLOCK_MODE,
        )
