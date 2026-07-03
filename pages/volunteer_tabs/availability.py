"""Volunteer My Availability tab."""

from application.services.volunteer_availability_service import VolunteerAvailabilityService
from theme.availability_editor import render_availability_editor


async def availability_tab() -> None:
    await render_availability_editor(
        VolunteerAvailabilityService(),
        help_text='Add the windows you can work.',
    )
