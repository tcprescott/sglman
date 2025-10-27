from nicegui import app, ui

from models import Permissions, User


class BaseLayout:
    """Base layout component providing header, footer, and tabbed content structure."""
    
    def __init__(
        self,
        copyright_text: str = "© 2025 Thomas Prescott",
        default_tab: str = None,
        tabs: list = None,
        user: User = None,
        **_kwargs  # Accept and ignore unused legacy params for backward compatibility
    ):
        self.copyright_text = copyright_text
        self.tabs = tabs
        self.default_tab = default_tab
        self.user = user
        self.dark_mode = None  # Will be initialized in render()
        
        # Build top menu based on user permissions
        self.top_menu: list[tuple[str, str]] = [('Home', '/')]
        if user and user.permission >= Permissions.TOURNAMENT_ADMIN:
            self.top_menu.append(('Admin', '/admin'))

    async def render(self) -> None:
        """Render the complete layout with header, footer, and optional tabbed content."""
        # Initialize dark mode controller and restore user's preference
        dark_pref = bool(app.storage.user.get('dark_mode', False))
        self.dark_mode = ui.dark_mode()
        self.dark_mode.value = dark_pref
        # Add custom CSS to all pages
        ui.add_head_html('<link rel="stylesheet" href="/static/css/styles.css">')
        self._render_header()
        self._render_footer()
        
        if self.tabs:
            await self.render_tabbed_page(self.tabs)
    
    def _render_header(self) -> None:
        """Render the header with navigation menu and user controls."""
        dark_pref = bool(app.storage.user.get('dark_mode', False))
        dark_btn_ref = {'btn': None}

        def toggle_dark_mode():
            self.dark_mode.value = not self.dark_mode.value
            app.storage.user['dark_mode'] = self.dark_mode.value
            # Update icon to reflect current state
            if dark_btn_ref['btn'] is not None:
                icon = 'light_mode' if self.dark_mode.value else 'dark_mode'
                dark_btn_ref['btn'].props(f"icon={icon}")
                dark_btn_ref['btn'].update()

        with ui.header().classes(replace='row items-center'):
            # Navigation menu
            for label, action in self.top_menu:
                ui.button(label, on_click=lambda a=action: ui.navigate.to(a)).props('flat color=white')

            # User section or login
            if self.user:
                ui.label(self.user.preferred_name).classes('text-lg user-name')
                ui.image(app.storage.user.get('avatar', None)).props(
                    'width=32 height=32 fit=cover round'
                ).classes('user-avatar')
                ui.button(on_click=lambda: ui.navigate.to('/logout'), icon='logout').props('flat color=white')
            else:
                ui.button(
                    on_click=lambda: ui.navigate.to('/login'),
                    icon='login',
                    text='Login with Discord'
                ).props('flat color=white').classes('login-button')
            
            # Dark mode toggle (always visible)
            dark_icon = 'light_mode' if dark_pref else 'dark_mode'
            dark_btn_ref['btn'] = ui.button(
                icon=dark_icon,
                on_click=toggle_dark_mode
            ).props('flat color=white').tooltip('Toggle dark mode')
    
    def _render_footer(self) -> None:
        """Render the footer with copyright text."""
        with ui.footer().classes('bg-grey-2 text-grey-7 q-pa-md footer-dark-override'):
            ui.label(self.copyright_text).classes('text-caption')

    async def render_tabbed_page(self, tabs: list) -> None:
        """Render a tabbed interface with the provided tab configuration.
        
        Args:
            tabs: List of tab dictionaries with 'label', 'icon' (optional), and 'content' keys.
                  Content can be a callable or tuple of (callable, args, kwargs).
        """
        import inspect
        
        def on_tab_change(event):
            """Update URL query param when tab changes."""
            ui.navigate.history.push(f'?tab={event.value}')

        # Determine default tab
        tab_labels = [tab['label'] for tab in tabs]
        default_tab = self.default_tab if self.default_tab in tab_labels else tabs[0]['label']

        async def render_tab_content(tab):
            """Render content for a single tab, handling both sync and async callables."""
            content = tab['content']
            
            # Parse content configuration
            if isinstance(content, tuple):
                content_func = content[0]
                args = content[1] if len(content) > 1 and content[1] is not None else ()
                kwargs = content[2] if len(content) > 2 and content[2] is not None else {}
            else:
                content_func = content
                args = ()
                kwargs = {}
            
            # Call content function (async or sync)
            if inspect.iscoroutinefunction(content_func):
                await content_func(*args, **kwargs)
            else:
                content_func(*args, **kwargs)

        # Render tabs navigation
        with ui.tabs(on_change=on_tab_change).props('horizontal').classes('w-full') as panels:
            for tab in tabs:
                ui.tab(tab['label'], icon=tab.get('icon'))
        
        # Render tab panels content
        with ui.tab_panels(panels, value=default_tab):
            for tab in tabs:
                with ui.tab_panel(tab['label']):
                    with ui.row().classes('full-width'):
                        await render_tab_content(tab)


