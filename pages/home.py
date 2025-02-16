from theme import theme

from nicegui import ui

def create() -> None:
    @ui.page('/')
    async def home():
        with theme.frame('Home'):
            theme.message('This is the home page.').classes('font-bold')
            ui.label('Use the menu on the top right to navigate.')