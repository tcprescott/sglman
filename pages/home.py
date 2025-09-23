from nicegui import app, ui
from theme.base import BaseLayout

def create() -> None:
    @ui.page('/')
    async def home():
        from models import User, Permissions
        discord_id = app.storage.user.get('discord_id', None)
        if not discord_id:
            ui.label('Welcome to SGLMan! Please log in to access more features.').style('font-size: 1.5em; margin-bottom: 1em;')
        user = await User.get_or_none(discord_id=discord_id)
        await BaseLayout(page_name='home', user=user).render()
