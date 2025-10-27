from nicegui import app, ui

from models import Permissions, User


class BaseLayout:
    def __init__(self, page_name, site_name: str = "SpeedGaming Live On Site", logo_url: str = None, copyright_text: str = "© 2025 Thomas Prescott", default_tab: str = None, tabs: list = None, user: User = None):
        self.site_name = site_name
        self.logo_url = logo_url
        self.copyright_text = copyright_text
        self.tabs = tabs
        self.default_tab = default_tab
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
        # Initialize dark mode controller and restore user's preference
        dark_pref = bool(app.storage.user.get('dark_mode', False))
        dm = ui.dark_mode()
        dm.value = dark_pref
        _dark_btn_ref = {'btn': None}  # holder to update icon on toggle

        def _toggle_dark_mode():
            dm.value = not dm.value
            app.storage.user['dark_mode'] = dm.value
            # update icon to reflect the opposite mode action
            if _dark_btn_ref['btn'] is not None:
                _dark_btn_ref['btn'].props(f"icon={'light_mode' if dm.value else 'dark_mode'}")
                _dark_btn_ref['btn'].update()

        with ui.header().classes(replace='row items-center'):
            if self.top_menu:
                for label, action in self.top_menu:
                    ui.button(label, on_click=lambda a=action: ui.navigate.to(a)).props('flat color=white')
            else:
                ui.button('Default', on_click=lambda: None).props('flat color=white')

            if self.user:
                ui.label(self.user.preferred_name).classes('text-lg').style('margin-left: auto;')
                ui.image(app.storage.user.get('avatar', None)).props('width=32 height=32 fit=cover round').style('margin-left: 8px; margin-right: 8px; display: inline-block; max-width: 32px; max-height: 32px; vertical-align: middle;')
                ui.button(on_click=lambda: ui.navigate.to('/logout'), icon='logout')
                _dark_btn_ref['btn'] = ui.button(icon=('light_mode' if dark_pref else 'dark_mode'), on_click=_toggle_dark_mode).props('flat color=white').tooltip('Toggle dark mode')
            else:
                ui.button(on_click=lambda: ui.navigate.to('/login'), icon='login', text='Login with Discord').style('margin-left: auto;')
                _dark_btn_ref['btn'] = ui.button(icon=('light_mode' if dark_pref else 'dark_mode'), on_click=_toggle_dark_mode).props('flat color=white').tooltip('Toggle dark mode')

        with ui.footer().classes('bg-grey-2 text-grey-7 q-pa-md'):
            ui.label(self.copyright_text).classes('text-caption')

        if self.tabs:
            await self.render_tabbed_page(self.tabs)

    async def render_tabbed_page(self, tabs):
        import inspect
        def on_tab_change(event):
            ui.navigate.history.push(f'?tab={event.value}')

        default_tab = self.default_tab if self.default_tab and self.default_tab in [tab['label'] for tab in tabs] else tabs[0]['label']

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

        tab_props = 'horizontal'
        tab_classes = 'w-full'
        with ui.tabs(on_change=on_tab_change).props(tab_props).classes(tab_classes) as panels:
            for tab in tabs:
                ui.tab(tab['label'], icon=tab.get('icon', None))
        with ui.tab_panels(panels, value=default_tab):
            for tab in tabs:
                with ui.tab_panel(tab['label']):
                    with ui.row().style('width: 100%;'):
                        await render_tab_content(tab)


