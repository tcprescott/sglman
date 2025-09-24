from nicegui import ui, app
from typing import Callable as func
from models import Permissions, User
from enum import Enum

class BaseLayout:
    def __init__(self, page_name, site_name: str = "SpeedGaming Live On Site", logo_url: str = None, copyright_text: str = "© 2025 Thomas Prescott", tabs: list = None, user: User = None):
        self.site_name = site_name
        self.logo_url = logo_url
        self.copyright_text = copyright_text
        self.tabs = tabs
        self.page_name = page_name
        self.user = user
        self.width = None

        if user and user.permission >= Permissions.TOURNAMENT_ADMIN:
            self.top_menu: list[tuple[str, str]] = [
                ('Home', '/'),
                ('Admin', '/admin'),
            ]
        else:
            self.top_menu: list[tuple[str, str]] = [
                ('Home', '/'),
            ]

    async def render(self) -> None:
        if self.width is None:
            self.width = await ui.run_javascript("window.screen.width;", timeout=10)
            self.width = int(self.width)
            app.storage.user['screen_width'] = self.width

        with ui.header().classes(replace='row items-center') as header:
            if self.top_menu:
                for label, action in self.top_menu:
                    ui.button(label, on_click=lambda a=action: ui.navigate.to(a)).props('flat color=white')
            else:
                ui.button('Default', on_click=lambda: None).props('flat color=white')

            if app.storage.user.get('authenticated', False):
                ui.label(f'Hello, {app.storage.user.get("username", "User")}!').classes('text-lg').style('margin-left: auto;')
                ui.button(on_click=lambda: ui.navigate.to('/logout'), icon='logout')
            else:
                ui.button(on_click=lambda: ui.navigate.to('/login'), icon='login', text='Login with Discord').style('margin-left: auto;')

        with ui.footer().classes('bg-grey-2 text-grey-7 q-pa-md') as footer:
            ui.label(self.copyright_text).classes('text-caption')

        with ui.page_sticky(position='bottom-right', x_offset=20, y_offset=20):
            ui.button(on_click=footer.toggle, icon='contact_support').props('fab')

        if self.tabs:
            await self.render_tabbed_page(self.tabs)

    async def render_tabbed_page(self, tabs):
        import inspect
        def on_tab_change(event):
            # Update URL query parameter to current tab
            if app.storage.user.get('selected_tab') is None:
                app.storage.user['selected_tab'] = {}
            app.storage.user['selected_tab'][self.page_name] = event.value

        default_tab = app.storage.user.get('selected_tab', {}).get(self.page_name, tabs[0]['label'])

        async def render_tab_content(tab):
            content = tab['content']
            if isinstance(content, tuple):
                content_func = content[0]
                args = content[1] if len(content) > 1 and content[1] is not None else ()
                kwargs = content[2] if len(content) > 2 and content[2] is not None else {}
            else:
                content_func = content
                args = ()
                kwargs = {}
            if inspect.iscoroutinefunction(content_func):
                await content_func(*args, **kwargs)
            else:
                content_func(*args, **kwargs)

        tab_props = 'horizontal' if self.width < 600 else 'vertical'
        tab_classes = 'w-full' if self.width < 600 else 'w-full'
        if self.width < 600:
            with ui.tabs(on_change=on_tab_change).props(tab_props).classes(tab_classes) as panels:
                for tab in tabs:
                    ui.tab(tab['label'], icon=tab.get('icon', None))
            with ui.tab_panels(panels, value=default_tab):
                for tab in tabs:
                    with ui.tab_panel(tab['label']):
                        with ui.row().classes('justify-center').style('width: 100%;'):
                            await render_tab_content(tab)
        else:
            with ui.splitter(value=5, limits=(5, 5)).classes('w-full h-full') as splitter:
                with splitter.before:
                    with ui.tabs(on_change=on_tab_change).props(tab_props).classes(tab_classes) as panels:
                        for tab in tabs:
                            ui.tab(tab['label'], icon=tab.get('icon', None))
                with splitter.after:
                    with ui.tab_panels(panels, value=default_tab):
                        for tab in tabs:
                            with ui.tab_panel(tab['label']):
                                with ui.row().classes('justify-center').style('width: 100%;'):
                                    await render_tab_content(tab)

