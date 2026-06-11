"""Volunteer Section Page (self-service for volunteers)."""

from nicegui import app, ui
from middleware.auth import protected_page

from application.services import AuthService
from models import User
from pages.volunteer_tabs.opt_in import opt_in_tab
from pages.volunteer_tabs.availability import availability_tab
from pages.volunteer_tabs.my_shifts import my_shifts_tab
from theme.base import BaseLayout


def create() -> None:
    @protected_page('/volunteer')
    async def volunteer_page(tab: str = None) -> None:
        ui.page_title('Speedgaming Live Onsite - Volunteer')
        discord_id = app.storage.user.get('discord_id', None)
        user = await User.get_or_none(discord_id=discord_id)
        if user is None:
            with ui.row():
                ui.label('You must be logged in to view this page.').classes('text-error')
            return

        tabs = [
            {'label': 'Opt-in', 'icon': 'how_to_reg', 'content': opt_in_tab},
            {'label': 'My Availability', 'icon': 'event_available', 'content': availability_tab},
            {'label': 'My Shifts', 'icon': 'assignment_ind', 'content': my_shifts_tab},
        ]
        show_admin = await AuthService.can_view_admin(user)
        await BaseLayout(
            tabs=tabs, default_tab=tab, page_name='volunteer', user=user,
            show_admin=show_admin, show_volunteer=True,
        ).render()
