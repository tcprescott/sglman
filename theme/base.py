import re

from nicegui import app, ui

from models import User


def tab_slug(label: str) -> str:
    """Derive a URL path segment from a tab's display label.

    Lowercases and collapses each run of non-alphanumeric characters to a
    single hyphen: ``"Vol. Roster"`` → ``vol-roster``, ``"On Air"`` → ``on-air``.
    Auto-derived slugs are collision-free within each page's label set; a tab
    dict may override with an explicit ``'slug'`` key if ever needed.
    """
    return re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')


class BaseLayout:
    """Base layout component providing header, drawer, footer, and tabbed content structure."""

    def __init__(
        self,
        copyright_text: str | None = None,
        section: str = None,
        base_path: str = None,
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
        self._bottom_tabs = None
        self._more_btn = None
        self._bottom_tab_labels: list = []
        self._syncing_nav = False
        self._tab_item_refs: dict = {}
        # Base URL (including any /t/<slug> root_path) that section slugs hang
        # off of, e.g. '/t/foo/admin'. None for tab-less pages, which never
        # rewrite the URL.
        self._base_path = base_path

        self.top_menu: list[dict] = [{'label': 'Home', 'icon': 'home', 'url': '/'}]
        if show_volunteer:
            self.top_menu.append({'label': 'Volunteer', 'icon': 'volunteer_activism', 'url': '/volunteer'})
        if show_admin:
            self.top_menu.append({'label': 'Admin', 'icon': 'admin_panel_settings', 'url': '/admin'})

        if tabs:
            # Sections are addressed in the URL by slug; internally everything
            # keys off the display label, so keep a slug↔label map for read-in
            # (path → default tab) and write-out (tab change → path).
            self._slug_by_label = {t['label']: t.get('slug') or tab_slug(t['label']) for t in tabs}
            self._label_by_slug = {slug: label for label, slug in self._slug_by_label.items()}
            self._default_tab = self._label_by_slug.get(section) or tabs[0]['label']
        else:
            self._slug_by_label = {}
            self._label_by_slug = {}
            self._default_tab = None

    async def render(self) -> None:
        """Render the complete layout with header, drawer, footer, and optional tabbed content."""
        self.render_chrome()
        if self.tabs:
            await self._render_tab_panels()

    def render_chrome(self) -> None:
        """Render the synchronous page frame (palette, header, drawer, footer).

        Split out from :meth:`render` so callers that cannot await — notably the
        synchronous ``on_page_exception`` error path — can still get the full
        themed chrome. Tab panels (the only async part) are rendered by
        :meth:`render`.
        """
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
        # PWA wiring: the manifest makes the app installable, the two media-scoped
        # theme-color metas tint the mobile browser/status-bar chrome to the gold
        # header (light) / charcoal (dark) palette, and the apple-touch-icon is the
        # iOS home-screen icon. The service worker is registered from the site root
        # (/sw.js, served in frontend.py) so its scope covers start_url '/'.
        ui.add_head_html('<link rel="manifest" href="/static/manifest.webmanifest">')
        ui.add_head_html(
            '<meta name="theme-color" content="#9C6B12" media="(prefers-color-scheme: light)">'
        )
        ui.add_head_html(
            '<meta name="theme-color" content="#17120D" media="(prefers-color-scheme: dark)">'
        )
        ui.add_head_html('<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">')
        ui.add_head_html(
            '<script>'
            "if('serviceWorker' in navigator){"
            "navigator.serviceWorker.register('/sw.js').catch(()=>{});"
            '}'
            '</script>'
        )
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
        # Konami code (↑↑↓↓←→←→BA) opens a hidden cat-fact dialog. The guard keeps
        # the window listener from being installed more than once across renders.
        ui.add_body_html(
            '<script>'
            'if(!window.__sglman_konami_installed){'
            'window.__sglman_konami_installed=true;'
            "const seq=['ArrowUp','ArrowUp','ArrowDown','ArrowDown',"
            "'ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','b','a'];"
            'let pos=0;'
            "window.addEventListener('keydown',function(e){"
            'const key=e.key.length===1?e.key.toLowerCase():e.key;'
            'if(key===seq[pos]){pos++;'
            "if(pos===seq.length){pos=0;emitEvent('sgl_konami',{});}}"
            'else{pos=(key===seq[0])?1:0;}'
            '});'
            '}'
            '</script>'
        )
        ui.on('sgl_konami', lambda _: self._open_cat_fact())
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

    def _open_cat_fact(self) -> None:
        from theme.dialog import CatFactDialog
        CatFactDialog().open()

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

        with ui.header().classes(replace='row items-center no-wrap sgl-header'):
            ui.button(
                icon='menu',
                on_click=lambda: self._drawer.toggle()
            ).props('flat color=white').classes('sgl-burger')

            wordmark_taps = {'n': 0}

            def on_wordmark_tap():
                from theme.dialog import CatFactDialog
                wordmark_taps['n'] += 1
                if wordmark_taps['n'] >= 5:
                    wordmark_taps['n'] = 0
                    CatFactDialog().open()

            ui.label('SGL On Site').classes('sgl-wordmark').on('click', on_wordmark_tap)

            # Flexible spacer that pushes the user/login controls to the right
            # edge. It must be a real element rather than margin-left:auto on the
            # name/login button, because the name is display:none on phones — the
            # spacer keeps the alignment identical to desktop in every state.
            ui.space()

            if self.user:
                ui.label(self.user.preferred_name).classes('text-lg user-name')
                avatar_url = app.storage.user.get('avatar')
                if avatar_url:
                    ui.image(avatar_url).props(
                        'width=32 height=32 fit=cover round'
                    ).classes('user-avatar')
                else:
                    # No avatar URL (mock-login sessions, or Discord users on the
                    # default avatar): show a placeholder glyph instead of an empty
                    # ui.image(None), which also renders a broken image + console error.
                    ui.icon('account_circle').classes('user-avatar user-avatar-placeholder')
                ui.button(on_click=lambda: ui.navigate.to('/logout'), icon='logout').props('flat color=white').tooltip('Log out')
            else:
                # The full-text "Login with Discord" button also lives in the page
                # body; here the label is a child element (not the q-btn text prop)
                # so it can be hidden on phones via .login-button-text without
                # fighting Quasar's `.block` utility. The tooltip keeps the
                # icon-only mobile button labelled for accessibility.
                login_btn = ui.button(
                    on_click=lambda: ui.navigate.to('/login'),
                    icon='login',
                ).props('flat color=white').classes('login-button')
                with login_btn:
                    ui.label('Login with Discord').classes('login-button-text')
                login_btn.tooltip('Login with Discord')

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
        from theme.dialog import FeedbackDialog

        # Unify the drawer's auto-show boundary with the app-shell <1024px break:
        # below it the bottom nav + burger carry navigation, at/above it the drawer
        # pins open (show-if-above). This matches the grid-card table breakpoint.
        # NiceGUI renders the drawer body (.q-drawer__content) as a flex column,
        # so a trailing ui.space() pushes the copyright to the foot of the drawer
        # when the nav fits, and it falls to the scroll-end when the nav is long.
        with ui.left_drawer(value=False).props('breakpoint=1023 show-if-above bordered') as self._drawer:
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

            if self.user:
                ui.separator()
                with ui.list().props('padding'):
                    with ui.item(
                        on_click=lambda: FeedbackDialog(self.user).open()
                    ).props('clickable v-ripple'):
                        with ui.item_section().props('avatar'):
                            ui.icon('feedback').props('size=sm')
                        with ui.item_section():
                            ui.item_label('Feedback')

            # Copyright and source link live at the foot of the drawer (every
            # page renders the drawer, so this replaces the old desktop-only
            # footer meta row).
            ui.space()
            with ui.row().classes('items-center q-px-md q-pb-xs no-wrap'):
                ui.icon('code').props('size=xs').classes('sgl-drawer-github-link')
                ui.link('GitHub', 'https://github.com/tcprescott/sglman', new_tab=True) \
                    .classes('text-caption sgl-drawer-github-link')
            ui.label(self._copyright).classes('text-caption q-px-md q-pb-md sgl-drawer-copyright')

    def _switch_tab(self, label: str) -> None:
        # Only move the panel; the drawer highlight and the /base/<slug> history
        # replace are handled centrally by _handle_tab_change so every entry point
        # (drawer, bottom nav, swipe) produces identical side effects and no loops.
        self._tab_panels.set_value(label)

    def _handle_tab_change(self) -> None:
        """Single sink for panel-value changes: sync the drawer highlight, the
        bottom-nav highlight, and the /base/<slug> section URL regardless of what
        drove the change (drawer item, bottom tab, or swipe). Registered after the
        panels are built so the initial deep-linked value does not fire a spurious
        history entry."""
        label = self._tab_panels.value
        for lbl, item in self._tab_item_refs.items():
            if lbl == label:
                item.props(add='active')
            else:
                item.props(remove='active')
        self._sync_bottom_nav(label)
        # replace(), not push(): tab switches (incl. every swipe) update the URL for
        # deep-linking/sharing without stacking history entries that would turn the
        # Back button into a per-tab trap on mobile. The section is a path segment
        # (/base/<slug>), not a query param, so the URL reads like an app route.
        if self._base_path is not None:
            ui.navigate.history.replace(f'{self._base_path}/{self._slug_by_label[label]}')

    def _sync_bottom_nav(self, label: str) -> None:
        """Highlight the active tab in the bottom nav. Tabs beyond the first four
        live behind the More button, so when the active tab is one of those, clear
        the tab highlight (avoids Quasar's 'no matching tab' warning) and mark More
        active instead."""
        if self._bottom_tabs is None:
            return
        in_bar = label in self._bottom_tab_labels
        # Guard: setting the bottom tab's value re-fires its own change handler.
        self._syncing_nav = True
        self._bottom_tabs.set_value(label if in_bar else None)
        self._syncing_nav = False
        if self._more_btn is not None:
            if in_bar:
                self._more_btn.props(remove='color=primary')
            else:
                self._more_btn.props(add='color=primary')

    def _on_bottom_tab(self) -> None:
        """A bottom-nav tab was tapped: drive the panel (which then routes through
        _handle_tab_change for the highlight/URL sync). Ignored while we are
        programmatically syncing the highlight to avoid a feedback loop."""
        if self._syncing_nav:
            return
        value = self._bottom_tabs.value
        if value and value != self._tab_panels.value:
            self._tab_panels.set_value(value)

    def _render_footer(self) -> None:
        """Render the app-shell bottom navigation for phones/tablets (<1024px).

        The footer is *only* the bottom nav: the first four tabs as a native tab
        row plus a More button that opens the drawer for the remaining tabs. On
        desktop the drawer carries navigation so the bar collapses away (via
        .sgl-bottom-nav). Copyright and Feedback live in the drawer, not here, so
        a tab-less page renders no footer at all rather than an empty strip.
        """
        if not self.tabs:
            return

        with ui.footer().classes('q-py-xs q-px-md footer-dark-override'):
            self._bottom_tab_labels = [tab['label'] for tab in self.tabs[:4]]
            # A deep link may open on a tab that lives behind More; seed the bar
            # with no active tab in that case so we never bind a value with no
            # matching child (which Quasar warns about and leaves unhighlighted).
            initial = self._default_tab if self._default_tab in self._bottom_tab_labels else None
            with ui.tabs(value=initial).props('dense no-caps').classes(
                'sgl-bottom-nav'
            ) as self._bottom_tabs:
                for tab in self.tabs[:4]:
                    ui.tab(tab['label'], icon=tab.get('icon', 'circle'))
                # The More affordance is a plain button, not a q-tab, so it carries
                # no value that could corrupt the tab binding.
                self._more_btn = ui.button(
                    'More',
                    icon='more_horiz',
                    on_click=lambda: self._drawer.toggle(),
                ).props('flat no-caps')
                if initial is None:
                    self._more_btn.props(add='color=primary')
            # Tapping a bottom tab drives the panel; the highlight/URL sync then
            # flows back through _handle_tab_change.
            self._bottom_tabs.on_value_change(self._on_bottom_tab)

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

        with ui.tab_panels(value=self._default_tab).props('swipeable animated').classes(
            'w-full'
        ) as self._tab_panels:
            for tab in self.tabs:
                with ui.tab_panel(tab['label']):
                    with ui.row().classes('full-width'):
                        await render_tab_content(tab)

        # Panel changes (drawer click, bottom-tab tap, or swipe) all route through
        # _handle_tab_change, which syncs both highlights and the URL. Registered
        # after construction so the initial deep-linked value does not fire it (no
        # spurious history entry). The bottom nav is kept in sync manually rather
        # than via bind_value, because a two-way bind would force the tab model to a
        # value with no matching child whenever the active tab lives behind More.
        self._tab_panels.on_value_change(self._handle_tab_change)
