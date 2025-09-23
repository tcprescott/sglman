from nicegui import app, ui
from theme.base import BaseLayout
from pages.schedule import schedule
from pages.player import render_edit_info_tab, render_player_dashboard
from pages.crew import render_crew_dashboard

def create() -> None:
    @ui.page('/')
    async def home():
        from models import User
        discord_id = app.storage.user.get('discord_id', None)
        user = await User.get_or_none(discord_id=discord_id)
        tabs = [
            {'label': 'Event Schedule', 'content': schedule},
            {'label': 'Your Matches', 'content': render_player_dashboard},
            {'label': 'Crew Signup', 'content': render_crew_dashboard},
            {'label': 'Your Information', 'content': render_edit_info_tab},
        ]
        await BaseLayout(tabs=tabs, page_name='home', user=user).render()
