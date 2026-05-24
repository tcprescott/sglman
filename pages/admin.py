"""Admin Dashboard Page"""

from nicegui import app, ui
from middleware.auth import protected_page

from pages.admin_tabs.admin_schedule import admin_schedule_page
from pages.admin_tabs.admin_settings import admin_stream_rooms_page, admin_tournaments_page
from pages.admin_tabs.admin_users import admin_users_page
from pages.admin_tabs.reports import reports_page
from models import Permissions, User
from theme.base import BaseLayout


def create() -> None:
    @protected_page('/admin')
    async def admin_dashboard_page(
        tab: str = None,
        report: str = None,
        start: str = None,
        end: str = None,
        tournament_id: int = None,
        user_id: int = None,
        stream_room_id: int = None,
        state: str = None,
        approval: str = None,
        action: str = None,
        focus: str = None,
        page: int = None,
    ) -> None:
        ui.page_title('Speedgaming Live Onsite - Admin Dashboard')
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            with ui.row():
                ui.label('You must be logged in to view this page.').classes('text-error')
            return

        user = await User.get_or_none(discord_id=discord_id)
        if user is None:
            with ui.row():
                ui.label('User not found in the database.').classes('text-error')
            return
        if user.permission < Permissions.TOURNAMENT_ADMIN:
            await BaseLayout(page_name='admin2').render()
            with ui.row():
                ui.label('You do not have permission to view this page.').classes('text-error')
            return

        reports_kwargs = {
            'report': report,
            'start': start,
            'end': end,
            'tournament_id': tournament_id,
            'user_id': user_id,
            'stream_room_id': stream_room_id,
            'state': state,
            'approval': approval,
            'action': action,
            'focus': focus,
            'page': page,
        }

        # Define tab data model: label and content function
        tabs = [
            {'label': 'Schedule', 'icon': 'schedule', 'content': admin_schedule_page},
            {'label': 'Users', 'icon': 'people', 'content': admin_users_page},
            {'label': 'Tournaments', 'icon': 'emoji_events', 'content': admin_tournaments_page},
            {'label': 'Stream Rooms', 'icon': 'tv', 'content': admin_stream_rooms_page},
            # {'label': 'Announcements', 'icon': 'announcement', 'content': announcement_admin_page},
            {'label': 'Reports', 'icon': 'analytics', 'content': (reports_page, (), reports_kwargs)},
        ]

        base_layout = BaseLayout(tabs=tabs, default_tab=tab, page_name='admin', user=user)
        await base_layout.render()
