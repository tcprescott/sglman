from nicegui import app, ui

from models import User
from pages.home_tabs.player_edit_info import render_edit_info_tab
from pages.home_tabs.player import render_player_dashboard
from pages.home_tabs.stage_timeline import stage_timeline_tab
from pages.home_tabs.schedule import schedule
from theme.base import BaseLayout


def create() -> None:
    @ui.page('/')
    async def home(tab: str = None):
        ui.page_title('Speedgaming Live Onsite')
        discord_id = app.storage.user.get('discord_id', None)
        user = await User.get_or_none(discord_id=discord_id)
        if user is None and discord_id is not None:
            with ui.row():
                # log the user out if they are not found in the database
                ui.label('User not found in the database. Logging out...').style('color: red; font-weight: bold;')
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
        await BaseLayout(tabs=tabs, default_tab=tab, page_name='home', user=user).render()
