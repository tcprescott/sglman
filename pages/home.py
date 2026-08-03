from fastapi import Request
from nicegui import app, ui

from application.services import AuthService, TenantService, get_user_from_discord_id
from application.tenant_context import (
    get_current_tenant_id,
    is_host_mode,
    stash_client_host_mode,
    stash_client_tenant_id,
)
from middleware.auth import bind_display_timezone, enforce_membership
from pages.home_tabs.event import event_tab
from pages.home_tabs.my_schedule import my_schedule_tab
from pages.home_tabs.player_edit_info import render_edit_info_tab
from pages.home_tabs.tournaments import tournaments_tab
from theme.assets import asset_url
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
    ui.add_head_html(f'<link rel="stylesheet" href="{asset_url("css/styles.css")}">')
    # This page builds its own chrome rather than BaseLayout's, so it repeats
    # the site-wide noindex (see theme/base.py).
    ui.add_head_html('<meta name="robots" content="noindex, nofollow">')
    ui.colors(
        primary='#9C6B12', secondary='#C24E12', accent='#E0A82E',
        positive='#557A1F', negative='#B3362B', warning='#B45309', info='#0E7470',
    )
    with ui.header().classes('wiz-header items-center no-wrap'):
        ui.label('Wizzrobe').classes('wiz-wordmark')
        # Flexible spacer pushes the login/user controls to the right edge (see
        # BaseLayout._render_header for the same pattern on tenant surfaces).
        ui.space()
        if user is not None:
            ui.label(user.preferred_name).classes('text-lg user-name')
            avatar_url = app.storage.user.get('avatar')
            if avatar_url:
                ui.image(avatar_url).props('width=32 height=32 fit=cover round').classes('user-avatar')
            else:
                # No avatar URL (mock-login sessions, or Discord users on the
                # default avatar): show a placeholder glyph rather than a broken image.
                ui.icon('account_circle').classes('user-avatar user-avatar-placeholder')
            ui.button(on_click=lambda: ui.navigate.to('/logout'), icon='logout') \
                .props('flat color=white').tooltip('Log out')
        else:
            login_btn = ui.button(
                on_click=lambda: ui.navigate.to('/login'),
                icon='login',
            ).props('flat color=white').classes('login-button')
            with login_btn:
                ui.label('Login with Discord').classes('login-button-text')
            login_btn.tooltip('Login with Discord')

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
    async def home(
        section: str | None = None,
        request: Request = None,
        schedule: int | None = None,
        reschedule: int | None = None,
        match: int | None = None,
    ):
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
        # Bind the display clock. Same reason this page applies the membership
        # gate itself: it is a bare ``ui.page``, so it never passes through
        # ``_tenant_page`` and gets nothing from it. Without this every tab below
        # — including the timezone picker on the Profile tab — renders on the
        # fallback zone no matter what the community or the viewer chose.
        await bind_display_timezone(tid, user)
        # The membership gate. This page is registered with a bare ``ui.page``
        # (the same function also renders the platform community picker, which
        # has no tenant and must stay anonymous), so it applies the gate itself
        # rather than getting it from ``_tenant_page``.
        #
        # This is where the audit measured the symptom: a platform user with no
        # roles and no membership loaded a brand-new community's home schedule,
        # saw its first match with both players' names, and was offered Sign Up
        # as commentator and tracker. The community's own spectator surface —
        # the bracket views — stays public on its own routes.
        if await enforce_membership(tid, user):
            return
        if user is None and discord_id is not None:
            with ui.row():
                # log the user out if they are not found / no longer active
                ui.label('User not found in the database. Logging out...').classes('text-error')
                app.storage.user.clear()
            ui.timer(2, lambda: ui.navigate.to('/logout'), once=True)
            return
        # Four tabs, on every community, whatever its feature flags. The count
        # used to run from five to ten, which meant no two communities' phone nav
        # looked alike and — because the bottom bar carries ``tabs[:4]`` and hides
        # the rest behind More — a player's own matches were off the bar entirely.
        # A feature that is off now removes a *view* or a *section*, never a tab.
        #
        # Each tab lists the slugs it absorbed. Those answer on read-in only, so
        # DMs already sent (docs/features/discord.md) keep landing where they
        # always did while the URL normalizes to the new slug on the first switch.
        tabs = [
            # `view` is the section slug the visitor arrived on: the Event tab
            # opens on the matching view, so /home/on-air and /home/brackets
            # still open On Air and Brackets rather than the board.
            {'label': 'Event', 'icon': 'event', 'aliases': ('schedule', 'on-air', 'brackets'),
             'content': (event_tab, (), {'view': section})},
            # `schedule` is a bracket matchup id: the matches section opens its
            # schedule dialog on arrival, so the "matchup ready" DM's button
            # lands on the date/time picker rather than on a page about it.
            # `reschedule` is a match id doing the same job for the declined
            # reschedule DM, whose next step is asking again with a new time.
            # `match` narrows the board to one match, for the stage DMs — the
            # player-side equivalent of `/admin/schedule?match_id=`.
            {'label': 'My Schedule', 'icon': 'event_available',
             'aliases': ('player', 'my-crew', 'availability', 'equipment'),
             'content': (my_schedule_tab, (),
                         {'schedule': schedule, 'reschedule': reschedule,
                          'match': match})},
            # Signing up is the step that comes before having a schedule at all,
            # and it used to be a checkbox on Profile that a player could use the
            # app for a season without ever finding. Triforce text submission
            # hangs off the card for the tournament it belongs to.
            {'label': 'Tournaments', 'icon': 'emoji_events', 'aliases': ('triforce-texts',),
             'content': tournaments_tab},
            {'label': 'Profile', 'icon': 'account_circle', 'content': render_edit_info_tab},
        ]
        show_admin = await AuthService.can_view_admin(user)
        base_path = f"{request.scope.get('root_path', '')}/home" if request else '/home'
        await BaseLayout(
            tabs=tabs, section=section, base_path=base_path, page_name='home', user=user,
            show_admin=show_admin,
        ).render()

    # Home is the tenant landing (`/`) and its sections hang off `/home/<slug>`,
    # matching the /admin/<slug> and /volunteer/<slug> hubs. Bare `/` renders the
    # default section (the URL stays `/` until the first tab switch).
    ui.page('/')(home)
    ui.page('/home')(home)
    ui.page('/home/{section}')(home)
