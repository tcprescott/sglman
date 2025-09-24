from nicegui import app, ui

from models import User
from pages.crew import render_crew_dashboard
from pages.player import render_edit_info_tab, render_player_dashboard
from pages.schedule import schedule
from theme.base import BaseLayout


def create() -> None:
    @ui.page('/')
    async def home():

        discord_id = app.storage.user.get('discord_id', None)
        user = await User.get_or_none(discord_id=discord_id)
        tabs = [
            {'label': 'Schedule', 'icon': 'schedule', 'content': schedule},
            {'label': 'Player', 'icon': 'videogame_asset', 'content': render_player_dashboard},
            {'label': 'Crew', 'icon': 'handyman', 'content': render_crew_dashboard},
            {'label': 'Profile', 'icon': 'people', 'content': render_edit_info_tab},
        ]
        await BaseLayout(tabs=tabs, page_name='home', user=user).render()
