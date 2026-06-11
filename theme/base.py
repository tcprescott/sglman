from nicegui import app, ui

from models import User


class BaseLayout:
    """Base layout component providing header, drawer, footer, and tabbed content structure."""

    def __init__(
        self,
        copyright_text: str | None = None,
        default_tab: str = None,
        tabs: list = None,
        user: User = None,
        show_admin: bool = False,
        show_volunteer: bool = False,
        **_kwargs
    ):
        self._copyright = copyright_text if copyright_text is not None else "© 2026 Thomas Prescott"
        self.tabs = tabs
        self.user = user
        self.dark_mode = None

        self._drawer = None
        self._tab_panels = None
        self._tab_item_refs: dict = {}

        self.top_menu: list[dict] = [{'label': 'Home', 'icon': 'home', 'url': '/'}]
        if show_volunteer:
            self.top_menu.append({'label': 'Volunteer', 'icon': 'volunteer_activism', 'url': '/volunteer'})
        if show_admin:
            self.top_menu.append({'label': 'Admin', 'icon': 'admin_panel_settings', 'url': '/admin'})

        if tabs:
            tab_labels = [tab['label'] for tab in tabs]
            self._default_tab = default_tab if default_tab in tab_labels else tabs[0]['label']
        else:
            self._default_tab = None

    async def render(self) -> None:
        """Render the complete layout with header, drawer, footer, and optional tabbed content."""
        dark_pref = app.storage.user.get('dark_mode')  # None ⇒ auto: match the client's system theme
        self.dark_mode = ui.dark_mode(dark_pref)
        # Preload only the above-the-fold fonts; the remaining weights load on demand.
        for font_file in (
            'atkinson-hyperlegible-latin-400-normal',
            'fraunces-latin-600-normal',
            'ibm-plex-mono-latin-400-normal',
        ):
            ui.add_head_html(
                f'<link rel="preload" href="/static/fonts/{font_file}.woff2" '
                'as="font" type="font/woff2" crossorigin>'
            )
        ui.add_head_html('<link rel="stylesheet" href="/static/css/styles.css">')
        ui.add_head_html(
            '<script>'
            'console.log('
            '"%c\U0001f3a2 SGL On Site%c — did you know? '
            'Cats have been known to ride roller coasters purely for the airtime.",'
            '"color:#E0A82E;font-weight:bold;font-size:14px",'
            '"color:#9C6B12"'
            ');'
            '</script>'
        )
        # Phoenix brand palette: gold primary, ember secondary; semantic colors
        # warm-tuned to match the --status-* tokens in styles.css so notify
        # toasts and negative buttons sit with the palette instead of stock
        # Material green/red.
        ui.colors(
            primary='#9C6B12',
            secondary='#C24E12',
            accent='#E0A82E',
            positive='#557A1F',
            negative='#B3362B',
            warning='#B45309',
            info='#0E7470',
        )
        self._render_header()
        self._render_drawer()
        self._render_footer()
        if self.tabs:
            await self._render_tab_panels()

    def _render_header(self) -> None:
        """Render the header with burger menu button and user controls."""
        dark_pref = app.storage.user.get('dark_mode')
        dark_btn_ref = {'btn': None}

        def toggle_dark_mode():
            self.dark_mode.value = not self.dark_mode.value
            app.storage.user['dark_mode'] = self.dark_mode.value
            if dark_btn_ref['btn'] is not None:
                icon = 'light_mode' if self.dark_mode.value else 'dark_mode'
                dark_btn_ref['btn'].props(f"icon={icon}")
                dark_btn_ref['btn'].update()

        with ui.header().classes(replace='row items-center sgl-header'):
            ui.button(
                icon='menu',
                on_click=lambda: self._drawer.toggle()
            ).props('flat color=white')
            ui.label('SGL On Site').classes('sgl-wordmark')

            if self.user:
                ui.label(self.user.preferred_name).classes('text-lg user-name')
                ui.image(app.storage.user.get('avatar', None)).props(
                    'width=32 height=32 fit=cover round'
                ).classes('user-avatar')
                ui.button(on_click=lambda: ui.navigate.to('/logout'), icon='logout').props('flat color=white').tooltip('Log out')
            else:
                ui.button(
                    on_click=lambda: ui.navigate.to('/login'),
                    icon='login',
                    text='Login with Discord'
                ).props('flat color=white').classes('login-button')

            dark_icon = (
                'brightness_auto' if dark_pref is None
                else 'light_mode' if dark_pref
                else 'dark_mode'
            )
            dark_btn_ref['btn'] = ui.button(
                icon=dark_icon,
                on_click=toggle_dark_mode
            ).props('flat color=white').tooltip('Toggle dark mode')

    def _render_drawer(self) -> None:
        """Render the left drawer with navigation links and optional tab navigation."""
        with ui.left_drawer(value=False).props('breakpoint=600 show-if-above bordered') as self._drawer:
            with ui.list().props('padding'):
                for item in self.top_menu:
                    with ui.item(on_click=lambda u=item['url']: ui.navigate.to(u)).props('clickable v-ripple'):
                        with ui.item_section().props('avatar'):
                            ui.icon(item['icon']).props('size=sm')
                        with ui.item_section():
                            ui.item_label(item['label'])

            if self.tabs:
                ui.separator()
                with ui.list().props('padding'):
                    for tab in self.tabs:
                        with ui.item(
                            on_click=lambda t=tab['label']: self._switch_tab(t)
                        ).props('clickable v-ripple') as tab_item:
                            with ui.item_section().props('avatar'):
                                ui.icon(tab.get('icon', 'circle')).props('size=sm')
                            with ui.item_section():
                                ui.item_label(tab['label'])
                        if tab['label'] == self._default_tab:
                            tab_item.props(add='active')
                        self._tab_item_refs[tab['label']] = tab_item

    def _switch_tab(self, label: str) -> None:
        for lbl, item in self._tab_item_refs.items():
            if lbl == label:
                item.props(add='active')
            else:
                item.props(remove='active')
        self._tab_panels.set_value(label)
        ui.navigate.history.push(f'?tab={label}')

    def _render_footer(self) -> None:
        """Render the footer with copyright text."""
        with ui.footer().classes('q-py-xs q-px-md footer-dark-override'):
            with ui.row().classes('w-full justify-between items-center'):
                ui.label(self._copyright).classes('text-caption')

    async def _render_tab_panels(self) -> None:
        """Render tab panel content with programmatically controlled panel switching."""
        import inspect

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

        with ui.tab_panels(value=self._default_tab).classes('w-full') as self._tab_panels:
            for tab in self.tabs:
                with ui.tab_panel(tab['label']):
                    with ui.row().classes('full-width'):
                        await render_tab_content(tab)
