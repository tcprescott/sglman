"""Home My Availability tab (self-service for any logged-in player)."""

from application.services.player_availability_service import PlayerAvailabilityService
from theme.availability_editor import render_availability_editor


async def availability_tab() -> None:
    await render_availability_editor(
        PlayerAvailabilityService(),
        help_text='Add the windows when you can play.',
    )
