from nicegui import app, ui
from theme.base import BaseLayout

def create() -> None:
    @ui.page('/')
    async def home():
        BaseLayout()

        # with ui.left_drawer().classes('bg-blue-100') as left_drawer:
        #     ui.label('Side menu')

