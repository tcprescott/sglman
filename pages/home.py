from theme import theme
from theme.message import message


from nicegui import ui

def create() -> None:
    @ui.page('/')
    def home():
        with theme.frame('Home'):
            theme.message('This is the home page.').classes('font-bold')
            ui.label('Use the menu on the top right to navigate.')