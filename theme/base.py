from nicegui import ui, app
from typing import Callable as func

class BaseLayout:
    def __init__(self, site_name: str = "SpeedGaming Live Administration System", logo_url: str = None, copyright_text: str = "© 2025 SGLMan", top_menu: list[tuple[str, func]] = None):
        self.site_name = site_name
        self.logo_url = logo_url
        self.copyright_text = copyright_text
        self.top_menu = top_menu

        with ui.header().classes(replace='row items-center') as header:
            ui.button(on_click=lambda: left_drawer.toggle(), icon='menu').props('flat color=white')
            if self.top_menu:
                with ui.tabs() as tabs:
                    for label, _ in self.top_menu:
                        ui.tab(label).props('flat color=white')
            else:
                with ui.tabs() as tabs:
                    ui.tab('Default').props('flat color=white')

            if app.storage.user.get('authenticated', False):
                ui.label(f'Hello, {app.storage.user.get("username", "User")}!').classes('text-lg').style('margin-left: auto;')
                ui.button(on_click=lambda: app.storage.user.clear() or ui.navigate.to('/logout'), icon='logout')
            else:
                ui.button(on_click=lambda: ui.navigate.to('/login'), icon='login').style('margin-left: auto;')

        with ui.footer().classes('bg-grey-2 text-grey-7 q-pa-md') as footer:
            ui.label(self.copyright_text).classes('text-caption')

        with ui.left_drawer().classes('bg-blue-100') as left_drawer:
            ui.label('Side menu')

        with ui.page_sticky(position='bottom-right', x_offset=20, y_offset=20):
            ui.button(on_click=footer.toggle, icon='contact_support').props('fab')

        with ui.tab_panels(tabs, value='A').classes('w-full'):
            if self.top_menu:
                for label, action in self.top_menu:
                    with ui.tab_panel(label):
                        action()
            else:
                with ui.tab_panel('Default'):
                    ui.label('No top menu defined.')

