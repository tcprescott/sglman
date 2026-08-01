import json
import logging
import re

from nicegui import app, ui

from application.table_preferences_context import table_prefs_scope
from application.tenant_context import get_current_tenant_id, tenant_scope
from models import FeatureFlag, User
from theme.chrome import dark_mode_button, install_timezone_detection
from theme.connection import install_connection_watch
from theme.notice import drain_notice

logger = logging.getLogger(__name__)


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
        section: str | None = None,
        base_path: str | None = None,
        tabs: list | None = None,
        user: User = None,
        show_admin: bool = False,
        show_volunteer: bool | None = None,
        wordmark: str | None = None,
        **_kwargs
    ):
        self._copyright = copyright_text if copyright_text is not None else "© 2026 Thomas Prescott"
        self.tabs = tabs
        self.user = user
        self.dark_mode = None
        # Header wordmark: the in-scope community's own name on a tenant surface,
        # 'Wizzrobe' on the platform. Resolved from the ambient tenant in render()
        # when a caller does not pass one explicitly.
        self._wordmark = wordmark
        # Resolved per-tenant brand palette, loaded in render() before chrome is
        # drawn. None on the synchronous error path (render_chrome without
        # render), where render_chrome falls back to the shipped defaults.
        self._theme_colors: dict[str, str] | None = None

        self._drawer = None
        self._tab_panels = None
        self._bottom_tabs = None
        self._more_btn = None
        self._bottom_tab_labels: list = []
        self._syncing_nav = False
        self._tab_item_refs: dict = {}
        # Lazy tab rendering: every panel gets a container up front, but its
        # content is built on first show. `_pending_tabs` holds the not-yet-built
        # tabs; a label leaves it exactly once, when its content is built.
        self._tab_containers: dict = {}
        self._pending_tabs: dict = {}
        # Captured at page-build time (the request context) and rebound around a
        # deferred build, which runs in an event handler with no tenant contextvar.
        self._tenant_id = get_current_tenant_id()
        # This viewer's saved table layouts, loaded once in render() and rebound
        # the same way. Empty until then, which means "the shipped columns".
        self._table_prefs: dict[str, dict] = {}
        # Base URL (including any /t/<slug> root_path) that section slugs hang
        # off of, e.g. '/t/foo/admin'. None for tab-less pages, which never
        # rewrite the URL.
        self._base_path = base_path

        # Nav visibility. `show_volunteer=None` (the default) means "resolve it
        # from the user's access" in render(), which is what every tenant page
        # wants — the link must not be offered where the tenant has the feature
        # off or the user holds none of the volunteer roles, or it dead-ends on a
        # 404/403. An explicit bool is honoured as-is, which keeps the synchronous
        # render_chrome() path (the error page) working without a DB round-trip.
        self._show_admin = show_admin
        self._show_volunteer = show_volunteer
        # Same shape as _show_volunteer: resolved in render() because the drawer
        # must not offer a Feedback item whose dialog the service would refuse.
        # False on the synchronous render_chrome() path (the error page), which
        # has no DB round-trip to spend and no need for the link.
        self._show_feedback = False
        self.top_menu: list[dict] = []

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
        # A message stashed before a redirect (theme/notice.py) is shown on the
        # first framed page the browser lands on, whichever that turns out to be.
        drain_notice()
        if self._wordmark is None:
            from application.services import TenantService
            self._wordmark = (await TenantService.current_community_name()) or 'Wizzrobe'
        if self._show_volunteer is None:
            from application.services import AuthService
            self._show_volunteer = await AuthService.can_view_volunteer(self.user)
        if self.user:
            from application.services import FeatureFlagService
            self._show_feedback = await FeatureFlagService().is_enabled(FeatureFlag.FEEDBACK)
        await self._load_theme_colors()
        # One query for every table on the page. Bound for the rest of the build
        # so each customize_table call reads it back synchronously — a table
        # build cannot await, and a page can host a dozen of them.
        from application.services import TablePreferenceService
        self._table_prefs = await TablePreferenceService().prime(self.user)
        with table_prefs_scope(self._table_prefs):
            self.render_chrome()
            if self.tabs:
                await self._render_tab_panels()

    async def _load_theme_colors(self) -> None:
        """Resolve the in-scope tenant's brand palette before drawing chrome.

        Best-effort and non-raising (the platform surface has no tenant); the
        service returns the shipped defaults when there is no tenant or no
        override. Imported lazily to keep this presentation module import-light.
        """
        from application.services import TenantThemeService
        self._theme_colors = await TenantThemeService.get_current_theme()

    def _build_top_menu(self) -> None:
        """Assemble the header/drawer nav. Deferred out of ``__init__`` so
        ``render`` can resolve Volunteer visibility (an async access check) first."""
        self.top_menu = [{'label': 'Home', 'icon': 'home', 'url': '/'}]
        if self._show_volunteer:
            self.top_menu.append({'label': 'Volunteer', 'icon': 'volunteer_activism', 'url': '/volunteer'})
        if self._show_admin:
            self.top_menu.append({'label': 'Admin', 'icon': 'admin_panel_settings', 'url': '/admin'})

    def render_chrome(self) -> None:
        """Render the synchronous page frame (palette, header, drawer, footer).

        Split out from :meth:`render` so callers that cannot await — notably the
        synchronous ``on_page_exception`` error path — can still get the full
        themed chrome. Tab panels (the only async part) are rendered by
        :meth:`render`.
        """
        self._build_top_menu()
        # Per-tenant brand palette (loaded in render(); shipped defaults on the
        # synchronous error path or the tenant-less platform surface).
        from application.services.tenant_theme_service import DEFAULT_THEME
        colors = self._theme_colors or DEFAULT_THEME

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
        # Paired with the site-wide robots.txt (frontend.py): the signed-out
        # surfaces are shareable by link, not published to search engines, and
        # robots.txt alone does not deindex a URL a crawler already knows.
        ui.add_head_html('<meta name="robots" content="noindex, nofollow">')
        # PWA wiring: the manifest makes the app installable, the two media-scoped
        # theme-color metas tint the mobile browser/status-bar chrome to the gold
        # header (light) / charcoal (dark) palette, and the apple-touch-icon is the
        # iOS home-screen icon. The service worker is registered from the site root
        # (/sw.js, served in frontend.py) so its scope covers start_url '/'.
        ui.add_head_html('<link rel="manifest" href="/static/manifest.webmanifest">')
        # Light-mode browser/status-bar tint follows the tenant's header colour;
        # dark mode keeps the charcoal bar (the header stays charcoal in dark).
        ui.add_head_html(
            f'<meta name="theme-color" content="{colors["header"]}" media="(prefers-color-scheme: light)">'
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
            '"%c\U0001f3a2 Wizzrobe%c — did you know? '
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
            'if(!window.__wizzrobe_konami_installed){'
            'window.__wizzrobe_konami_installed=true;'
            "const seq=['ArrowUp','ArrowUp','ArrowDown','ArrowDown',"
            "'ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','b','a'];"
            'let pos=0;'
            "window.addEventListener('keydown',function(e){"
            'const key=e.key.length===1?e.key.toLowerCase():e.key;'
            'if(key===seq[pos]){pos++;'
            "if(pos===seq.length){pos=0;emitEvent('wiz_konami',{});}}"
            'else{pos=(key===seq[0])?1:0;}'
            '});'
            '}'
            '</script>'
        )
        ui.on('wiz_konami', lambda _: self._open_cat_fact())
        install_timezone_detection()
        # A dropped socket eats a click silently; this makes the page say so.
        install_connection_watch()
        # Drag-to-resize headers on any table carrying data-wiz-table-key. In the
        # head, not the body, for the same reason as install_connection_watch:
        # markup added from a lazy tab build never executes its <script>.
        ui.add_head_html('<script src="/static/js/table-columns.js"></script>')
        # Phoenix brand palette: gold primary, ember secondary — overridable per
        # tenant (theme/base loads TenantThemeService.get_current_theme). Semantic
        # colors stay fixed, warm-tuned to match the --status-* tokens in
        # styles.css so notify toasts and negative buttons sit with the palette
        # instead of stock Material green/red.
        ui.colors(
            primary=colors['primary'],
            secondary=colors['secondary'],
            accent=colors['accent'],
            positive='#557A1F',
            negative='#B3362B',
            warning='#B45309',
            info='#0E7470',
        )
        # ui.colors only recolors Quasar's palette; the header bar, links, and
        # section titles read the --wiz-* brand vars from styles.css. Re-point
        # those to the tenant palette here (loaded after the stylesheet, so this
        # wins). --wiz-header-bg is set on :root for the light bar; the dark
        # rule in styles.css re-points it to charcoal on <body>, which stays
        # authoritative in dark mode. The two dark text-tint rules mirror the
        # !important defaults in styles.css so primary/secondary text follows the
        # tenant accent/secondary in dark mode too.
        ui.add_head_html(
            '<style>'
            ':root{'
            f'--wiz-gold-deep:{colors["primary"]};'
            f'--wiz-gold:{colors["accent"]};'
            f'--wiz-ember-deep:{colors["secondary"]};'
            f'--wiz-ember:{colors["secondary"]};'
            f'--wiz-header-bg:{colors["header"]};'
            '}'
            '.body--dark .text-primary,.q-dark .text-primary{color:var(--wiz-gold)!important;}'
            '.body--dark .text-secondary,.q-dark .text-secondary{color:var(--wiz-ember)!important;}'
            '</style>'
        )
        self._render_header()
        self._render_drawer()
        self._render_footer()

    def _open_cat_fact(self) -> None:
        from theme.dialog import CatFactDialog
        CatFactDialog().open()

    def _render_header(self) -> None:
        """Render the header with burger menu button and user controls."""
        with ui.header().classes(replace='row items-center no-wrap wiz-header'):
            ui.button(
                icon='menu',
                on_click=lambda: self._drawer.toggle()
            ).props('flat color=white').classes('wiz-burger')

            wordmark_taps = {'n': 0}

            def on_wordmark_tap():
                from theme.dialog import CatFactDialog
                wordmark_taps['n'] += 1
                if wordmark_taps['n'] >= 5:
                    wordmark_taps['n'] = 0
                    CatFactDialog().open()

            ui.label(self._wordmark or 'Wizzrobe').classes('wiz-wordmark').on('click', on_wordmark_tap)

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

            dark_mode_button(self.dark_mode)

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
                    current_group = None
                    for tab in self.tabs:
                        # Section headers for grouped drawers (admin passes a
                        # 'group' per tab); ungrouped pages render a flat list.
                        group = tab.get('group')
                        if group and group != current_group:
                            current_group = group
                            ui.item_label(group).props('header').classes('wiz-drawer-group')
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

            # Feedback is flag-gated: no item where the community has it off,
            # because the dialog's submit would be refused by the service.
            if self.user and self._show_feedback:
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
                ui.icon('code').props('size=xs').classes('wiz-drawer-github-link')
                ui.link('GitHub', 'https://github.com/tcprescott/wizzrobe', new_tab=True) \
                    .classes('text-caption wiz-drawer-github-link')
            ui.label(self._copyright).classes('text-caption q-px-md q-pb-md wiz-drawer-copyright')

    def _switch_tab(self, label: str) -> None:
        # Only move the panel; the drawer highlight and the /base/<slug> history
        # replace are handled centrally by _handle_tab_change so every entry point
        # (drawer, bottom nav, swipe) produces identical side effects and no loops.
        self._tab_panels.set_value(label)

    async def _handle_tab_change(self) -> None:
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
        # Done before the (possibly awaited) first build so the URL lands promptly.
        if self._base_path is not None:
            ui.navigate.history.replace(f'{self._base_path}/{self._slug_by_label[label]}')
        # First visit builds the panel, which loads its own data — broadcasting
        # ``selected_tab`` as well would make it fetch twice. Afterwards the panel
        # already exists, so the broadcast is what refreshes it.
        if await self._build_tab(label):
            return
        # Notify the newly-shown tab so it can refresh its data. Tabs listen via
        # ``ui.on('selected_tab', ...)`` (see theme/tables/admin_crud.wire_tab_refresh
        # and the per-tab wiring in pages/admin_tabs/*); every listener filters on its
        # own label, so a single broadcast reaches exactly the active tab. Emitted
        # client-side via the global emitEvent so e.args is the plain label string.
        ui.run_javascript(f"emitEvent('selected_tab', {json.dumps(label)})")

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
        .wiz-bottom-nav). Copyright and Feedback live in the drawer, not here, so
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
                'wiz-bottom-nav'
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

    @staticmethod
    async def _render_tab_content(tab: dict) -> None:
        """Invoke one tab's content callable, sync or async, with its optional
        ``(func, args, kwargs)`` tuple form."""
        import inspect

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

    async def _build_tab(self, label: str, *, deferred: bool = True) -> bool:
        """Build a tab's content the first time it is shown. Returns whether it
        built now (``False`` means it was already built, or the label is unknown).

        The tenant captured at page-build time is rebound around the build: a
        deferred build runs inside a websocket event handler, where the tenant
        contextvar is unset and only the client stash would answer — the same
        hazard, and the same fix, as ``admin_crud.wire_tab_refresh``.

        ``deferred`` distinguishes a post-load build (gets a spinner, because the
        user is waiting on it) from the initial in-page build of the visible tab.
        """
        tab = self._pending_tabs.pop(label, None)
        if tab is None:
            return False
        container = self._tab_containers[label]
        spinner = None
        if deferred:
            with container:
                spinner = ui.spinner(size='lg').classes('q-ma-md')
        try:
            with container:
                with tenant_scope(self._tenant_id), table_prefs_scope(self._table_prefs):
                    await self._render_tab_content(tab)
        except Exception:
            logger.exception('Failed to build tab %r', label)
            with container:
                ui.label('This section failed to load. Try switching tabs again.') \
                    .classes('text-negative q-ma-md')
        finally:
            if spinner is not None:
                container.remove(spinner)
        return True

    async def _render_tab_panels(self) -> None:
        """Build the panel shells, then fill in only the visible one.

        Every ``ui.tab_panel`` container is created up front so panel switching,
        deep-linked sections, and swipe all keep working, but a tab's *content* is
        built the first time that tab is shown. The home page carries up to nine
        tabs and a viewer sees one, so eager rendering spent ~47% of the page's
        render CPU on panels nobody looked at
        (docs/plans/single-worker-escape-plan.md §1.3).
        """
        with ui.tab_panels(value=self._default_tab).props('swipeable animated').classes(
            'w-full'
        ) as self._tab_panels:
            for tab in self.tabs:
                with ui.tab_panel(tab['label']):
                    self._tab_containers[tab['label']] = ui.row().classes('full-width')
                self._pending_tabs[tab['label']] = tab

        await self._build_tab(self._default_tab, deferred=False)

        # Panel changes (drawer click, bottom-tab tap, or swipe) all route through
        # _handle_tab_change, which syncs both highlights and the URL. Registered
        # after construction so the initial deep-linked value does not fire it (no
        # spurious history entry). The bottom nav is kept in sync manually rather
        # than via bind_value, because a two-way bind would force the tab model to a
        # value with no matching child whenever the active tab lives behind More.
        self._tab_panels.on_value_change(self._handle_tab_change)
