"""Admin → Settings: every community setting in one place, behind its own menu.

Settings used to be eight drawer tabs (Settings, Features, Appearance, Timezone,
Role Mappings, Discord Events, Webhooks, Randomizer Keys) interleaved with the
day-to-day tools, and the one called Settings was a 2,000px column with two
Save buttons that each wrote a different half of it. Now the drawer has one
Settings entry and this page has a short menu of panes, each a stack of cards
that save on their own.

Panes are addressed as ``/admin/settings/<pane>``. The retired tab slugs
(``/admin/appearance`` and the rest) resolve to the pane that now holds them,
because DM buttons and bookmarks outlive the tabs they pointed at.
"""

import json
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from nicegui import app, ui

from application.services import AuthService, get_user_from_discord_id
from application.table_preferences_context import current_table_prefs, table_prefs_scope
from application.tenant_context import get_current_tenant_id, tenant_scope
from application.timezone_context import current_timezone_name, tz_scope
from models import FeatureFlag
from pages.admin_tabs.admin_discord_events import admin_discord_events_page
from pages.admin_tabs.admin_discord_roles import admin_discord_roles_page
from pages.admin_tabs.admin_features import admin_features_page
from pages.admin_tabs.admin_randomizer_keys import admin_randomizer_keys_page
from pages.admin_tabs.admin_theme import admin_theme_page
from pages.admin_tabs.admin_timezone import admin_timezone_page
from pages.admin_tabs.admin_webhooks import admin_webhooks_page
from pages.admin_tabs.settings.event import event_settings_pane
from pages.admin_tabs.settings.members import members_settings_pane
from pages.admin_tabs.settings.venue import venue_settings_pane
from pages.admin_tabs.settings.volunteers import volunteers_settings_pane
from theme.page_header import nested_page_headers, page_header

#: The admin drawer label, and so the ``selected_tab`` value this page hears.
SETTINGS_TAB_LABEL = 'Settings'

#: Retired admin tab slug → the pane that holds it now.
LEGACY_TAB_PANES: dict[str, str] = {
    'appearance': 'general',
    'timezone': 'general',
    'features': 'features',
    'role-mappings': 'discord',
    'discord-events': 'discord',
    'webhooks': 'integrations',
    'randomizer-keys': 'integrations',
}


@dataclass(frozen=True)
class EmbeddedPage:
    """A page that used to be its own tab, now one card of a pane."""

    render: Callable[..., Awaitable[None]]
    kwargs: dict = field(default_factory=dict)
    #: The old tab label its ``wire_tab_refresh`` listens for.
    refresh_label: Optional[str] = None


@dataclass(frozen=True)
class SettingsPane:
    slug: str
    label: str
    icon: str
    subtitle: str
    #: A pane built from cards of its own; takes ``can_edit``.
    native: Optional[Callable[[bool], Awaitable[None]]] = None
    embedded: tuple[EmbeddedPage, ...] = ()

    @property
    def refresh_labels(self) -> tuple[str, ...]:
        return tuple(p.refresh_label for p in self.embedded if p.refresh_label)


def build_settings_panes(access, live: set) -> list[SettingsPane]:
    """The panes this viewer may open, in menu order.

    Pure, like ``build_admin_tabs``, so who-sees-what is testable without a
    browser. Each pane keeps the role gate its old tab had: a sync admin still
    reaches Discord Events and a preset manager still reaches Randomizer Keys,
    and they see only those.
    """
    is_staff = access.is_staff
    panes: list[SettingsPane] = []
    if is_staff:
        panes.append(SettingsPane(
            'general', 'General', 'tune',
            'How the community looks, and the clock it tells time by.',
            embedded=(EmbeddedPage(admin_theme_page), EmbeddedPage(admin_timezone_page)),
        ))
        panes.append(SettingsPane(
            'event', 'Event', 'event',
            'When the event runs and how much of it runs at once.',
            native=event_settings_pane,
        ))
        panes.append(SettingsPane(
            'venue', 'Venue', 'chair',
            'The stations in the room and the screens on its walls.',
            native=venue_settings_pane,
        ))
        panes.append(SettingsPane(
            'members', 'Members', 'group_add',
            'Who can join, and what everyone else sees.',
            native=members_settings_pane,
        ))
        if FeatureFlag.VOLUNTEERS in live:
            panes.append(SettingsPane(
                'volunteers', 'Volunteers', 'volunteer_activism',
                'Shift reminders and the hours that earn rewards.',
                native=volunteers_settings_pane,
            ))
    discord: list[EmbeddedPage] = []
    if is_staff:
        discord.append(EmbeddedPage(
            admin_discord_roles_page, {'volunteer_mappings': FeatureFlag.VOLUNTEERS in live},
            refresh_label='Role Mappings',
        ))
    if is_staff or access.is_sync_admin:
        discord.append(EmbeddedPage(admin_discord_events_page, refresh_label='Discord Events'))
    if discord:
        panes.append(SettingsPane(
            'discord', 'Discord', 'forum',
            'The linked server, which of its roles mean what here, and the events mirrored into it.',
            embedded=tuple(discord),
        ))
    integrations: list[EmbeddedPage] = []
    if is_staff:
        integrations.append(EmbeddedPage(admin_webhooks_page, refresh_label='Webhooks'))
    if is_staff or access.is_preset_manager:
        integrations.append(EmbeddedPage(admin_randomizer_keys_page, refresh_label='Randomizer Keys'))
    if integrations:
        panes.append(SettingsPane(
            'integrations', 'Integrations', 'extension',
            'Other services this community sends to or signs in to.',
            embedded=tuple(integrations),
        ))
    if is_staff:
        panes.append(SettingsPane(
            'features', 'Features', 'toggle_on',
            'Turn parts of the app on or off for this community.',
            embedded=(EmbeddedPage(admin_features_page),),
        ))
    return panes


def resolve_pane(panes: list[SettingsPane], requested: Optional[str]) -> Optional[SettingsPane]:
    """The pane a URL asks for, else the first one; a stale name is not an error."""
    if not panes:
        return None
    by_slug = {p.slug: p for p in panes}
    slug = LEGACY_TAB_PANES.get(requested or '', requested)
    return by_slug.get(slug or '') or panes[0]


async def admin_settings_page(
    panes: list[SettingsPane],
    pane: Optional[str] = None,
    base_path: str = '/admin',
) -> None:
    current = resolve_pane(panes, pane)
    if current is None:
        return
    can_edit = await AuthService.is_staff(
        await get_user_from_discord_id(app.storage.user.get('discord_id')))
    # Captured now: a pane built later is built inside a click handler, which
    # has lost the tenant, the display zone and the table layouts.
    tenant_id = get_current_tenant_id()
    tz = current_timezone_name()
    prefs = current_table_prefs()

    containers: dict[str, ui.element] = {}
    built: set[str] = set()
    nav_items: dict[str, ui.item] = {}
    state = {'slug': current.slug}

    async def build(p: SettingsPane) -> None:
        built.add(p.slug)
        with containers[p.slug], tenant_scope(tenant_id), tz_scope(tz), table_prefs_scope(prefs):
            page_header(p.label, p.subtitle)
            if p.native is not None:
                await p.native(can_edit)
            for page in p.embedded:
                with ui.element('section').classes('wiz-panel wiz-settings-embed'), nested_page_headers():
                    await page.render(**page.kwargs)

    def sync_url() -> None:
        ui.navigate.history.replace(f'{base_path}/settings/{state["slug"]}')

    async def show(p: SettingsPane) -> None:
        state['slug'] = p.slug
        for slug, item in nav_items.items():
            item.props(add='active') if slug == p.slug else item.props(remove='active')
        for slug, container in containers.items():
            container.set_visibility(slug == p.slug)
        sync_url()
        if p.slug not in built:
            await build(p)
            return
        for label in p.refresh_labels:
            ui.run_javascript(f"emitEvent('selected_tab', {json.dumps(label)})")

    with ui.element('div').classes('wiz-settings'):
        with ui.element('nav').classes('wiz-settings__nav').props('aria-label="Settings"'):
            with ui.list().props('dense').classes('wiz-settings__menu'):
                for p in panes:
                    with ui.item(on_click=lambda _e=None, p=p: show(p)).classes(
                        'wiz-settings__item'
                    ) as item:
                        if p is current:
                            item.props('active')
                        with ui.item_section().props('avatar'):
                            ui.icon(p.icon)
                        with ui.item_section():
                            ui.label(p.label)
                    nav_items[p.slug] = item
        with ui.element('div').classes('wiz-settings__content'):
            for p in panes:
                containers[p.slug] = ui.column().classes('wiz-settings__pane wiz-section-stack')
                containers[p.slug].set_visibility(p is current)

    await build(current)

    def on_admin_tab(e) -> None:
        # Coming back to Settings from another admin tab: the layout has just
        # rewritten the URL to /admin/settings, and the open pane's embedded
        # pages want the refresh their own tab used to get.
        if e.args != SETTINGS_TAB_LABEL:
            return
        sync_url()
        for label in next(p for p in panes if p.slug == state['slug']).refresh_labels:
            ui.run_javascript(f"emitEvent('selected_tab', {json.dumps(label)})")

    ui.on('selected_tab', on_admin_tab)
