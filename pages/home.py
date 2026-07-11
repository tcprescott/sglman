from nicegui import app, ui

from application.services import AuthService, get_user_from_discord_id
from pages.home_tabs.availability import availability_tab
from pages.home_tabs.equipment import equipment_tab
from pages.home_tabs.player_edit_info import render_edit_info_tab
from pages.home_tabs.player import render_player_dashboard
from pages.home_tabs.stage_timeline import stage_timeline_tab
from pages.home_tabs.schedule import schedule
from pages.home_tabs.triforce_texts import triforce_texts_tab
from theme.base import BaseLayout


def create() -> None:
    @ui.page('/')
    async def home(tab: str = None):
        ui.page_title('Speedgaming Live Onsite')
        discord_id = app.storage.user.get('discord_id', None)
        # get_user_from_discord_id enforces is_active, so a deactivated account
        # is treated as logged-out here too (uniform with /admin, /equipment,
        # the login flow, and the REST API) rather than still being shown its
        # personalized home and admin/volunteer nav affordances.
        user = await get_user_from_discord_id(discord_id)
        if user is None and discord_id is not None:
            with ui.row():
                # log the user out if they are not found / no longer active
                ui.label('User not found in the database. Logging out...').classes('text-error')
                app.storage.user.clear()
            ui.timer(2, lambda: ui.navigate.to('/logout'), once=True)
            return
        tabs = [
            # {'label': 'Home', 'icon': 'home', 'content': announcements_page},
            {'label': 'Schedule', 'icon': 'schedule', 'content': schedule},
            {'label': 'On Air', 'icon': 'live_tv', 'content': stage_timeline_tab},
            {'label': 'Profile', 'icon': 'people', 'content': render_edit_info_tab},
            {'label': 'Player', 'icon': 'videogame_asset', 'content': render_player_dashboard},
        ]
        if user is not None:
            tabs.append({'label': 'My Availability', 'icon': 'event_available', 'content': availability_tab})
            tabs.append({'label': 'Triforce Texts', 'icon': 'svguse:/static/triforce.svg#triforce|0 0 512 512', 'content': triforce_texts_tab})
            tabs.append({'label': 'Equipment', 'icon': 'inventory_2', 'content': equipment_tab})
        show_admin = await AuthService.can_view_admin(user)
        show_volunteer = user is not None
        await BaseLayout(
            tabs=tabs, default_tab=tab, page_name='home', user=user,
            show_admin=show_admin, show_volunteer=show_volunteer,
        ).render()
