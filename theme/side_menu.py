"""The side menu and the phone bottom bar.

The menu lists every area the viewer can open (Home, Watch, Volunteer,
Check-in, Admin) as an accordion: an area opens in place to its sections, and
Admin opens a second level, its groups. A member's **Pinned** block sits on
top, and the first four pins, plus a Menu button, are the phone's bottom bar on
every page. Pins and which sections are open are saved per member per community
(``NavPreferenceService``).

Every hub is still its own page. A section of the page you are on switches in
place, as the drawer always did; a section of another hub navigates to its
``/<hub>/<slug>`` URL, which opens that page on that section.

A hub that is not the current page learns its sections from a resolver its
page module registers (:func:`register_hub_sections`), so this module never
imports ``pages/`` and a page that is not loaded (a unit test) just shows the
hub as a plain link.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from nicegui import ui

from application.tenant_context import tenant_scope
from models import User
from theme.nav_badges import nav_count_badge

if TYPE_CHECKING:
    from theme.base import BaseLayout

logger = logging.getLogger(__name__)

#: How many pins the phone's bottom bar carries before its Menu button.
BOTTOM_BAR_PINS = 4

#: Bottom-bar names for the labels too long for a fifth of a phone's width.
#: Anything not listed uses its own label.
SHORT_NAMES: dict[str, str] = {
    'My Schedule': 'My Schd',
    'Admin Schedule': 'Adm Schd',
    'Tournaments': 'Tourneys',
    'My Availability': 'Avail',
    'My Shifts': 'Shifts',
    'Proctor Station': 'Proctor',
    'Triforce Texts': 'Triforce',
    'Vol. Roster': 'Roster',
    'Vol. Schedule': 'Vol Schd',
    'Community Events': 'Comm Evts',
    'Service Health': 'Health',
    'SpeedGaming': 'SG',
    'Qualifiers': 'Quals',
    'Challonge': 'Challnge',
}

#: Admin's groups, in drawer order, with the icon on each group's row.
GROUP_ICONS: dict[str, str] = {
    'Operations': 'assignment',
    'Online play': 'language',
    'Community': 'diversity_3',
    'System': 'settings_applications',
}

_MENU = '__menu__'


def tab_slug(label: str) -> str:
    """Derive a URL path segment from a tab's display label.

    Lowercases and collapses each run of non-alphanumeric characters to a
    single hyphen: ``"Vol. Roster"`` → ``vol-roster``, ``"On Air"`` → ``on-air``.
    Auto-derived slugs are collision-free within each page's label set; a tab
    dict may override with an explicit ``'slug'`` key if ever needed.
    """
    return re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')


@dataclass(frozen=True)
class NavEntry:
    """One place the menu can take you: a hub section or a top-level page."""

    path: str
    label: str
    icon: str
    hub: str = ''
    group: Optional[str] = None
    badge: Optional[int] = None

    @property
    def short(self) -> str:
        return SHORT_NAMES.get(self.label, self.label)


@dataclass
class NavHub:
    """One area of the app; ``entries`` empty makes it a plain link."""

    key: str
    label: str
    icon: str
    path: str
    entries: list[NavEntry] = field(default_factory=list)


HubResolver = Callable[[User], Awaitable[list[dict]]]
_RESOLVERS: dict[str, HubResolver] = {}


def register_hub_sections(key: str, resolver: HubResolver) -> None:
    """Let the menu list hub ``key``'s sections on pages other than its own.

    ``resolver(user)`` returns the hub's tab dicts (``label``, ``icon``, and
    optionally ``group``, ``slug``, ``badge``) as the viewer would see them on
    the hub page. Content callables in them are ignored.
    """
    _RESOLVERS[key] = resolver


def entries_from_tabs(hub: str, tabs: list[dict]) -> list[NavEntry]:
    return [
        NavEntry(
            path=f"/{hub}/{t.get('slug') or tab_slug(t['label'])}",
            label=t['label'], icon=t.get('icon', 'circle'), hub=hub,
            group=t.get('group'), badge=t.get('badge'),
        )
        for t in tabs
    ]


def default_open_sections(hub: Optional[str], group: Optional[str]) -> set[str]:
    """What starts open for someone who never opened or closed a section: where they are."""
    if not hub:
        return set()
    return {hub, f'{hub}:{group}'} if group else {hub}


class SideMenu:
    """The drawer's navigation and the phone bottom bar for one page build."""

    def __init__(self, layout: 'BaseLayout', hub: Optional[str]) -> None:
        self._layout = layout
        self._hub = hub
        self._entries: dict[str, list[NavEntry]] = {}
        self._pins: list[str] = []
        self._open: Optional[set[str]] = None
        self._editing = False
        self._active: Optional[str] = None
        self._refs: dict[str, list[ui.item]] = {}
        self._bar: Optional[ui.tabs] = None
        self._syncing_bar = False

    # ------------------------------------------------------------- loading

    async def load(self) -> None:
        """Fetch other hubs' sections and the member's saved menu. Never raises."""
        layout = self._layout
        user = layout.user
        if user is None or layout._tenant_id is None:
            return
        shown = {'home': layout.is_member, 'volunteer': bool(layout._show_volunteer),
                 'admin': bool(layout._show_admin)}
        for key, visible in shown.items():
            if not visible or key == self._hub or key not in _RESOLVERS:
                continue
            try:
                self._entries[key] = entries_from_tabs(key, await _RESOLVERS[key](user))
            except Exception:
                logger.exception('Side menu could not list the %s sections', key)
        if layout.is_member:
            from application.services import NavPreferenceService
            try:
                pins, open_sections = await NavPreferenceService().load(user)
            except Exception:
                logger.exception('Side menu could not load saved pins')
                return
            self._pins = pins
            self._open = set(open_sections) if open_sections is not None else None

    # --------------------------------------------------------------- model

    def _hubs(self) -> list[NavHub]:
        layout = self._layout
        if self._hub and layout.tabs:
            self._entries[self._hub] = entries_from_tabs(self._hub, layout.tabs)
        hubs = [NavHub('home', 'Home', 'home', '/', self._entries.get('home', []) if layout.is_member else [])]
        if layout._tenant_id is not None:
            hubs.append(NavHub('watch', 'Watch', 'live_tv', '/live'))
        if layout._show_volunteer:
            hubs.append(NavHub('volunteer', 'Volunteer', 'volunteer_activism', '/volunteer',
                               self._entries.get('volunteer', [])))
        if layout._show_check_in:
            hubs.append(NavHub('checkin', 'Check-in', 'how_to_reg', '/checkin'))
        if layout._show_admin:
            hubs.append(NavHub('admin', 'Admin', 'admin_panel_settings', '/admin',
                               self._entries.get('admin', [])))
        return hubs

    def _destinations(self) -> dict[str, NavEntry]:
        """Everything pinnable, by path."""
        out: dict[str, NavEntry] = {}
        for hub in self._hubs():
            if hub.entries:
                for entry in hub.entries:
                    out[entry.path] = entry
            elif hub.key != 'home':
                out[hub.path] = NavEntry(path=hub.path, label=hub.label, icon=hub.icon)
        return out

    def pinned(self) -> list[NavEntry]:
        """The member's pins they can still reach, in their order."""
        destinations = self._destinations()
        return [destinations[p] for p in self._pins if p in destinations]

    def _open_set(self) -> set[str]:
        if self._open is not None:
            return self._open
        group = None
        if self._hub and self._layout.tabs:
            current = next((t for t in self._layout.tabs if t['label'] == self._layout._default_tab), None)
            group = current.get('group') if current else None
        return default_open_sections(self._hub, group)

    # ----------------------------------------------------------- rendering

    def render(self) -> None:
        """The drawer's navigation lists. Call inside the drawer."""
        if self._hub and self._layout._default_tab:
            self._active = self._path_for_tab(self._layout._default_tab)
        else:
            self._active = self._current_path()
        self._drawer_body()

    @ui.refreshable_method
    def _drawer_body(self) -> None:
        self._refs = {}
        layout = self._layout
        if layout.is_member and layout.user is not None:
            self._render_pinned()
        with ui.list().props('padding').classes('wiz-side-nav').props('data-usage-area="side menu"'):
            open_set = self._open_set()
            for hub in self._hubs():
                if not hub.entries:
                    pinnable = hub.key != 'home'
                    entry = NavEntry(path=hub.path, label=hub.label, icon=hub.icon)
                    self._entry_item(entry, pinnable=pinnable, target=hub.path)
                    continue
                with ui.expansion(hub.label, icon=hub.icon, value=hub.key in open_set).classes(
                        'wiz-nav-hub') as exp:
                    exp.on_value_change(lambda e, k=hub.key: self._set_open(k, e.value))
                    groups = [g for g in dict.fromkeys(e.group for e in hub.entries)]
                    if groups == [None]:
                        for entry in hub.entries:
                            self._entry_item(entry, depth=1)
                        continue
                    for group in groups:
                        key = f'{hub.key}:{group}'
                        with ui.expansion(group or 'More', icon=GROUP_ICONS.get(group or '', 'folder'),
                                          value=key in open_set).classes('wiz-nav-group') as sub:
                            sub.on_value_change(lambda e, k=key: self._set_open(k, e.value))
                            for entry in hub.entries:
                                if entry.group == group:
                                    self._entry_item(entry, depth=2)

    def _render_pinned(self) -> None:
        pins = self.pinned()
        with ui.list().props('padding').classes('wiz-side-pins').props('data-usage-area="pinned"'):
            ui.item_label('Pinned').props('header').classes('wiz-drawer-group')
            if not pins:
                ui.item_label('Nothing pinned yet.').classes('wiz-side-empty')
            last = len(pins) - 1
            for i, entry in enumerate(pins):
                with self._entry_item(entry, pinnable=False):
                    if self._editing:
                        with ui.item_section().props('side').classes('wiz-pin-tools'):
                            with ui.row().classes('no-wrap gap-0'):
                                self._tool('arrow_upward', f'Move {entry.label} up',
                                           lambda p=entry.path: self._move(p, -1), disabled=i == 0)
                                self._tool('arrow_downward', f'Move {entry.label} down',
                                           lambda p=entry.path: self._move(p, 1), disabled=i == last)
                                self._tool('close', f'Unpin {entry.label}',
                                           lambda p=entry.path: self._toggle_pin(p))
            if self._editing:
                ui.item_label(f'The first {BOTTOM_BAR_PINS} show in the bottom bar on a phone.') \
                    .classes('wiz-side-empty')
            with ui.item(on_click=self._toggle_editing).props('clickable v-ripple'):
                with ui.item_section().props('avatar'):
                    ui.icon('check' if self._editing else 'edit').props('size=sm')
                with ui.item_section():
                    ui.item_label('Done' if self._editing else 'Edit pins')
        ui.separator()

    def _entry_item(self, entry: NavEntry, *, depth: int = 0, pinnable: bool = True,
                    target: Optional[str] = None) -> ui.item:
        with ui.item(on_click=lambda e=entry: self._go(e)).props('clickable v-ripple').classes(
                f'wiz-nav-depth-{depth}') as item:
            with ui.item_section().props('avatar'):
                ui.icon(entry.icon).props('size=sm')
            with ui.item_section():
                ui.item_label(entry.label).props('lines=1')
            if entry.badge is not None and not self._editing:
                with ui.item_section().props('side'):
                    nav_count_badge(entry.label, entry.badge)
            if pinnable and self._editing and self._layout.is_member:
                pinned = entry.path in self._pins
                with ui.item_section().props('side').classes('wiz-pin-tools'):
                    self._tool('push_pin', f'{"Unpin" if pinned else "Pin"} {entry.label}',
                               lambda p=entry.path: self._toggle_pin(p),
                               classes='wiz-pin-on' if pinned else 'wiz-pin-off')
        self._refs.setdefault(target or entry.path, []).append(item)
        if (target or entry.path) == self._active:
            item.props(add='active')
        return item

    @staticmethod
    def _tool(icon: str, name: str, handler: Callable, *, disabled: bool = False,
              classes: str = '') -> ui.button:
        btn = ui.button(icon=icon, color=None).props('flat round dense size=sm').classes(
            f'wiz-pin-tool {classes}')
        btn.props(f'aria-label="{name}"')
        if disabled:
            btn.props('disable')
        # .stop: the button sits inside a clickable menu row, which would navigate.
        btn.on('click.stop', lambda _: handler())
        return btn

    @ui.refreshable_method
    def _bar_tabs(self) -> None:
        pins = self.pinned()[:BOTTOM_BAR_PINS]
        paths = {e.path for e in pins}
        value = self._active if self._active in paths else None
        with ui.tabs(value=value).props('dense no-caps').classes('wiz-bottom-nav').props(
                'data-usage-area="bottom bar"') as self._bar:
            for entry in pins:
                with ui.tab(entry.path, label=entry.short, icon=entry.icon) as tab:
                    tab.props(f'aria-label="{entry.label}"')
                    if entry.badge is not None:
                        nav_count_badge(entry.label, entry.badge).props('floating')
            ui.tab(_MENU, label='Menu', icon='menu').props('aria-label="Menu"')
        self._bar.on_value_change(self._on_bar)

    def render_bottom_bar(self) -> None:
        """The phone's bottom bar: the first pins, then Menu. Members only."""
        if not self._layout.is_member or self._layout.user is None:
            return
        ui.query('body').classes(add='wiz-has-bottom-nav')
        with ui.footer().classes('q-py-xs q-px-md footer-dark-override'):
            self._bar_tabs()

    # -------------------------------------------------------------- actions

    def _path_for_tab(self, label: str) -> Optional[str]:
        if not self._hub:
            return None
        slug = self._layout._slug_by_label.get(label)
        return f'/{self._hub}/{slug}' if slug else None

    def _current_path(self) -> Optional[str]:
        from theme.base import current_local_url
        return current_local_url().split('?', 1)[0]

    def tab_changed(self, label: str) -> None:
        """The current hub switched to ``label``: move the highlights."""
        path = self._path_for_tab(label)
        self._active = path
        for p, items in self._refs.items():
            for item in items:
                if p == path:
                    item.props(add='active')
                else:
                    item.props(remove='active')
        self._set_bar_value(path)

    def _set_bar_value(self, path: Optional[str]) -> None:
        if self._bar is None:
            return
        pins = {e.path for e in self.pinned()[:BOTTOM_BAR_PINS]}
        self._syncing_bar = True
        self._bar.set_value(path if path in pins else None)
        self._syncing_bar = False

    def _on_bar(self) -> None:
        if self._syncing_bar or self._bar is None:
            return
        value = self._bar.value
        if value == _MENU:
            self._layout._drawer.toggle()
            self._set_bar_value(self._active)
            return
        entry = self._destinations().get(value or '')
        if entry is not None and value != self._active:
            self._go(entry)

    def _go(self, entry: NavEntry) -> None:
        layout = self._layout
        if entry.hub and entry.hub == self._hub and entry.label in layout._slug_by_label:
            layout._switch_tab(entry.label)
            if layout._drawer is not None:
                ui.run_javascript(
                    f'if (window.innerWidth < 1024) runMethod({layout._drawer.id}, "hide", [])')
            return
        ui.navigate.to(entry.path)

    def _toggle_editing(self) -> None:
        self._editing = not self._editing
        self._drawer_body.refresh()

    async def _toggle_pin(self, path: str) -> None:
        pins = list(self._pins)
        if path in pins:
            pins.remove(path)
        else:
            pins.append(path)
        await self._save_pins(pins)

    async def _move(self, path: str, step: int) -> None:
        pins = list(self._pins)
        if path not in pins:
            return
        i = pins.index(path)
        j = i + step
        if not 0 <= j < len(pins):
            return
        pins[i], pins[j] = pins[j], pins[i]
        await self._save_pins(pins)

    async def _save_pins(self, pins: list[str]) -> None:
        from application.services import NavPreferenceService
        try:
            with tenant_scope(self._layout._tenant_id):
                self._pins = await NavPreferenceService().save_pins(self._layout.user, pins)
        except ValueError as e:
            ui.notify(str(e), color='warning')
            return
        self._drawer_body.refresh()
        if self._bar is not None:
            self._bar_tabs.refresh()

    async def _set_open(self, key: str, value: bool) -> None:
        open_set = set(self._open_set())
        if value:
            open_set.add(key)
        else:
            open_set.discard(key)
        self._open = open_set
        if not self._layout.is_member or self._layout.user is None:
            return
        from application.services import NavPreferenceService
        try:
            with tenant_scope(self._layout._tenant_id):
                await NavPreferenceService().save_open_sections(self._layout.user, sorted(open_set))
        except ValueError:
            logger.debug('open sections not saved', exc_info=True)
