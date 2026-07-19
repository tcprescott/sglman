from fastapi import Request
from nicegui import app, ui

from application.services import AuthService, FeatureFlagService, TenantService, get_user_from_discord_id
from application.tenant_context import (
    get_current_tenant_id,
    is_host_mode,
    stash_client_host_mode,
    stash_client_tenant_id,
)
from models import FeatureFlag
from pages.home_tabs.availability import availability_tab
from pages.home_tabs.equipment import equipment_tab
from pages.home_tabs.player_edit_info import render_edit_info_tab
from pages.home_tabs.player import render_player_dashboard
from pages.home_tabs.stage_timeline import stage_timeline_tab
from pages.home_tabs.schedule import schedule
from pages.home_tabs.triforce_texts import triforce_texts_tab
from theme.base import BaseLayout


async def _render_platform_landing() -> None:
    """The bare platform host (no /t/<slug>) shows a community picker.

    Runs with no tenant context: lists active tenants (each linking to its
    path-mode home) and, for a super-admin, a link to the /platform surface."""
    ui.page_title('Wizzrobe')
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    tenants = [t for t in await TenantService.list_tenants() if t.is_active]

    # Phoenix brand chrome. The picker is the platform's front door (bare host,
    # no tenant), so it can't reuse the tenant BaseLayout drawer; apply the same
    # stylesheet + palette + header so first impression reads as the product.
    ui.dark_mode(app.storage.user.get('dark_mode'))
    ui.add_head_html('<link rel="stylesheet" href="/static/css/styles.css">')
    ui.colors(
        primary='#9C6B12', secondary='#C24E12', accent='#E0A82E',
        positive='#557A1F', negative='#B3362B', warning='#B45309', info='#0E7470',
    )
    with ui.header().classes('wiz-header items-center'):
        ui.label('Wizzrobe').classes('wiz-wordmark')

    with ui.column().classes('w-full max-w-2xl mx-auto p-6 gap-4 items-stretch'):
        ui.label('Choose a community').classes('page-title')
        ui.label('Pick the community you want to manage or take part in.') \
            .classes('text-muted')
        if not tenants:
            ui.label('No communities are available yet.').classes('text-muted')
        with ui.column().classes('w-full gap-3'):
            for tenant in tenants:
                with ui.link(target=f'/t/{tenant.slug}/').classes('no-underline w-full'):
                    with ui.card().classes('wiz-tenant-card w-full'):
                        with ui.row().classes('items-center justify-between no-wrap w-full'):
                            with ui.column().classes('gap-0'):
                                ui.label(tenant.name).classes('wiz-tenant-name')
                                ui.label(f'/t/{tenant.slug}').classes('text-caption text-muted')
                            ui.icon('arrow_forward').classes('text-primary')
        if await AuthService.is_super_admin(user):
            ui.separator().classes('separator-spacing')
            ui.button('Platform administration', icon='admin_panel_settings',
                      on_click=lambda: ui.navigate.to('/platform')) \
                .props('outline color=primary')


def create() -> None:
    async def home(section: str = None, request: Request = None):
        # Bare platform host (no /t/<slug>) -> community picker, not a tenant home.
        tid = get_current_tenant_id()
        if tid is None:
            await _render_platform_landing()
            return
        # Stash the tenant onto the connection so websocket UI handlers resolve it.
        stash_client_tenant_id(tid)
        # Carry host mode too, so link-section buttons can hide on a custom domain.
        stash_client_host_mode(is_host_mode())

        ui.page_title(await TenantService.current_community_name() or 'Wizzrobe')
        discord_id = app.storage.user.get('discord_id', None)
        # get_user_from_discord_id enforces is_active, so a deactivated account
        # is treated as logged-out here too (uniform with /admin, /equipment,
        # the login flow, and the REST API) rather than still being shown its
        # personalized home and admin/volunteer nav affordances.
        user = await get_user_from_discord_id(discord_id)
        if user is None and discord_id is not None:
            with ui.row():
                # log the user out if they are not found / no longer active
                ui.label('User not found in the database. Logging out...').classes('text-error')
                app.storage.user.clear()
            ui.timer(2, lambda: ui.navigate.to('/logout'), once=True)
            return
        tabs = [
            # {'label': 'Home', 'icon': 'home', 'content': announcements_page},
            {'label': 'Schedule', 'icon': 'schedule', 'content': schedule},
            {'label': 'On Air', 'icon': 'live_tv', 'content': stage_timeline_tab},
            {'label': 'Profile', 'icon': 'people', 'content': render_edit_info_tab},
            {'label': 'Player', 'icon': 'videogame_asset', 'content': render_player_dashboard},
        ]
        if user is not None:
            # My Availability is intentionally ungated — availability feeds crew
            # signup too, not only volunteer scheduling. Triforce Texts and
            # Equipment are hidden unless the tenant has that feature enabled.
            live = await FeatureFlagService().enabled_flags()
            tabs.append({'label': 'My Availability', 'icon': 'event_available', 'content': availability_tab})
            if FeatureFlag.TRIFORCE_TEXTS in live:
                tabs.append({'label': 'Triforce Texts', 'icon': 'svguse:/static/triforce.svg#triforce|0 0 512 512', 'content': triforce_texts_tab})
            if FeatureFlag.EQUIPMENT in live:
                tabs.append({'label': 'Equipment', 'icon': 'inventory_2', 'content': equipment_tab})
        show_admin = await AuthService.can_view_admin(user)
        show_volunteer = user is not None
        base_path = f"{request.scope.get('root_path', '')}/home" if request else '/home'
        await BaseLayout(
            tabs=tabs, section=section, base_path=base_path, page_name='home', user=user,
            show_admin=show_admin, show_volunteer=show_volunteer,
        ).render()

    # Home is the tenant landing (`/`) and its sections hang off `/home/<slug>`,
    # matching the /admin/<slug> and /volunteer/<slug> hubs. Bare `/` renders the
    # default section (the URL stays `/` until the first tab switch).
    ui.page('/')(home)
    ui.page('/home')(home)
    ui.page('/home/{section}')(home)
