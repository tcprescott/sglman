"""Platform (super-admin) surface at ``/platform``.

Served on the bare platform host with **no** tenant context and gated to the
global ``SUPER_ADMIN`` role. Manages tenant CRUD (name, slug, domain, guild id,
active). Runs tenant-agnostically — its queries pass explicit ids, so the
per-tenant scoping never applies.
"""

from nicegui import app, ui

from application.services import (
    FeatureFlagService,
    RacetimeBotService,
    ServiceHealthService,
    TenantService,
    get_user_from_discord_id,
)
from application.services.auth_service import AuthService
from application.feature_flags import all_specs, spec_for
from application.tenant_context import get_current_tenant_id
from models import FeatureFlag

_bot_service = RacetimeBotService()

# Shared active-column icon slot (check_circle / cancel), matching the styled
# admin tables. Rows must carry an ``active_bool`` boolean.
_ACTIVE_ICON_SLOT = '''
    <q-td :props="props">
        <q-icon :name="props.row.active_bool ? 'check_circle' : 'cancel'"
                :color="props.row.active_bool ? 'positive' : 'negative'" size="sm" />
    </q-td>
'''

# Colored bot-health chip, shared by the desktop status cell and the mobile card
# so the two never drift. Rows must carry ``status`` (text) and ``status_kind``.
_BOT_STATUS_CHIP = '''
    <span class="sgl-chip" :class="{
        'sgl-chip--ok': props.row.status_kind === 'connected',
        'sgl-chip--cancelled': props.row.status_kind === 'error' || props.row.status_kind === 'disconnected',
        'sgl-chip--neutral': props.row.status_kind === 'unknown'
    }">{{ props.row.status }}</span>
'''


def _render_platform_chrome() -> None:
    """Phoenix brand chrome for the standalone platform surface.

    /platform runs on the bare host with no tenant, so it can't reuse the
    tenant BaseLayout (whose drawer links into /admin, /volunteer). Instead we
    apply the same stylesheet, palette, and a minimal branded header with a link
    back to the community picker — so the super-admin surface reads as the same
    product, not a default-Quasar scaffold.
    """
    dark_pref = app.storage.user.get('dark_mode')
    ui.dark_mode(dark_pref)
    ui.add_head_html('<link rel="stylesheet" href="/static/css/styles.css">')
    ui.colors(
        primary='#9C6B12', secondary='#C24E12', accent='#E0A82E',
        positive='#557A1F', negative='#B3362B', warning='#B45309', info='#0E7470',
    )
    with ui.header().classes('sgl-header items-center'):
        ui.label('SGL On Site').classes('sgl-wordmark')
        ui.label('· Platform').classes('sgl-wordmark text-caption').style('opacity:0.75')
        ui.space()
        with ui.link(target='/').classes('no-underline'):
            with ui.row().classes('items-center no-wrap').style('color:#fff;gap:4px'):
                ui.icon('arrow_back').props('size=sm')
                ui.label('Communities')


def create() -> None:
    @ui.page('/platform')
    async def platform() -> None:
        from theme.error_page import render_error_page

        # /platform is a platform-level page: reached via /t/<slug>/platform it
        # would carry a tenant — that is not a tenant page, so 404.
        if get_current_tenant_id() is not None:
            render_error_page(
                status_code=404, headline='Not Found',
                message='The platform surface lives at the bare host.', user=None,
            )
            return

        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        if not await AuthService.is_super_admin(user):
            render_error_page(
                status_code=403, headline='Forbidden',
                message='Platform administration requires super-admin.', user=user,
            )
            return

        ui.page_title('Platform Administration')
        _render_platform_chrome()
        with ui.column().classes('w-full max-w-5xl mx-auto p-6 gap-4'):
            with ui.row().classes('w-full items-center justify-between'):
                ui.label('Platform Administration').classes('page-title')
                ui.button('New tenant', icon='add', on_click=lambda: _open_create_dialog(user, table)).props('color=primary')

            columns = [
                {'name': 'id', 'label': 'ID', 'field': 'id', 'align': 'left'},
                {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
                {'name': 'slug', 'label': 'Slug (/t/…)', 'field': 'slug', 'align': 'left'},
                {'name': 'domain', 'label': 'Domain', 'field': 'domain', 'align': 'left'},
                {'name': 'guild', 'label': 'Guild', 'field': 'guild', 'align': 'left'},
                {'name': 'active', 'label': 'Active', 'field': 'active', 'align': 'left'},
                {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
            ]
            table = ui.table(columns=columns, rows=[], row_key='id').classes(
                'w-full sgl-table').props(':grid="Quasar.Screen.lt.md"')
            table.add_slot('body-cell-active', _ACTIVE_ICON_SLOT)
            table.add_slot('body-cell-actions', '''
                <q-td :props="props">
                    <q-btn dense flat color="primary" label="Edit"
                           @click="$parent.$emit('edit', props.row)" />
                    <q-btn dense flat color="secondary" label="Features"
                           @click="$parent.$emit('features', props.row)" />
                </q-td>
            ''')
            table.add_slot('item', '''
                <div class="q-pa-xs col-xs-12 col-sm-6">
                    <q-card bordered flat class="q-pa-sm sgl-grid-card">
                        <div class="row items-center justify-between no-wrap q-mb-xs">
                            <div class="text-weight-bold">{{ props.row.name }}</div>
                            <q-icon :name="props.row.active_bool ? 'check_circle' : 'cancel'"
                                    :color="props.row.active_bool ? 'positive' : 'negative'" size="sm">
                                <q-tooltip>{{ props.row.active_bool ? 'Active' : 'Inactive' }}</q-tooltip>
                            </q-icon>
                        </div>
                        <div class="text-caption text-grey-7 q-mb-xs">#{{ props.row.id }} · /t/{{ props.row.slug }}</div>
                        <div class="row q-mb-xs">
                            <div class="col-4 text-grey-7 text-caption">Domain</div>
                            <div class="col-8" style="overflow-wrap:anywhere">{{ props.row.domain }}</div>
                        </div>
                        <div class="row q-mb-xs">
                            <div class="col-4 text-grey-7 text-caption">Guild</div>
                            <div class="col-8" style="overflow-wrap:anywhere">{{ props.row.guild }}</div>
                        </div>
                        <div class="row justify-end q-gutter-x-sm q-mt-xs">
                            <q-btn dense flat color="primary" label="Edit"
                                   @click="$parent.$emit('edit', props.row)" />
                            <q-btn dense flat color="secondary" label="Features"
                                   @click="$parent.$emit('features', props.row)" />
                        </div>
                    </q-card>
                </div>
            ''')

            async def _on_edit(e) -> None:
                # Awaited by NiceGUI within the client's slot context (not a
                # background task), so ui.* calls in the dialog are safe.
                await _open_edit_dialog(user, table, e.args)

            async def _on_features(e) -> None:
                await _open_tenant_features_dialog(user, e.args)

            table.on('edit', _on_edit)
            table.on('features', _on_features)

            await _refresh(table)

            ui.separator().classes('q-my-lg')

            with ui.row().classes('w-full items-center justify-between'):
                ui.label('Racetime Bots').classes('section-title')
                ui.button('New bot', icon='add', on_click=lambda: _open_bot_create_dialog(user, bot_table)).props('color=primary')
            ui.label(
                'Shared, platform-managed bots — one per racetime category. Grant a '
                "bot to a tenant to let its sync admins select it on a tournament. "
                'Client secrets are write-only and never shown.'
            ).classes('text-caption text-grey')

            bot_columns = [
                {'name': 'id', 'label': 'ID', 'field': 'id', 'align': 'left'},
                {'name': 'category', 'label': 'Category', 'field': 'category', 'align': 'left', 'sortable': True},
                {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left'},
                {'name': 'client_id', 'label': 'Client ID', 'field': 'client_id', 'align': 'left'},
                {'name': 'active', 'label': 'Active', 'field': 'active', 'align': 'left'},
                {'name': 'status', 'label': 'Health', 'field': 'status', 'align': 'left'},
                {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
            ]
            bot_table = ui.table(columns=bot_columns, rows=[], row_key='id').classes(
                'w-full sgl-table').props(':grid="Quasar.Screen.lt.md"')
            bot_table.add_slot('body-cell-active', _ACTIVE_ICON_SLOT)
            bot_table.add_slot('body-cell-status', f'<q-td :props="props">{_BOT_STATUS_CHIP}</q-td>')
            bot_table.add_slot('body-cell-actions', '''
                <q-td :props="props">
                    <q-btn dense flat color="primary" label="Edit"
                           @click="$parent.$emit('edit_bot', props.row)" />
                    <q-btn dense flat color="secondary" label="Tenants"
                           @click="$parent.$emit('grant_bot', props.row)" />
                    <q-btn dense flat color="orange" label="Restart"
                           @click="$parent.$emit('restart_bot', props.row)" />
                </q-td>
            ''')
            bot_table.add_slot('item', '''
                <div class="q-pa-xs col-xs-12 col-sm-6">
                    <q-card bordered flat class="q-pa-sm sgl-grid-card">
                        <div class="row items-center justify-between no-wrap q-mb-xs">
                            <div class="text-weight-bold">{{ props.row.category }}</div>
                            <q-icon :name="props.row.active_bool ? 'check_circle' : 'cancel'"
                                    :color="props.row.active_bool ? 'positive' : 'negative'" size="sm">
                                <q-tooltip>{{ props.row.active_bool ? 'Active' : 'Inactive' }}</q-tooltip>
                            </q-icon>
                        </div>
                        <div class="text-caption text-grey-7 q-mb-xs">#{{ props.row.id }} · {{ props.row.name }}</div>
                        <div class="row q-mb-xs">
                            <div class="col-4 text-grey-7 text-caption">Client ID</div>
                            <div class="col-8" style="overflow-wrap:anywhere">{{ props.row.client_id }}</div>
                        </div>
                        <div class="row items-center q-mb-xs">
                            <div class="col-4 text-grey-7 text-caption">Health</div>
                            <div class="col-8">''' + _BOT_STATUS_CHIP + '''</div>
                        </div>
                        <div class="row justify-end q-gutter-x-sm q-mt-xs">
                            <q-btn dense flat color="primary" label="Edit"
                                   @click="$parent.$emit('edit_bot', props.row)" />
                            <q-btn dense flat color="secondary" label="Tenants"
                                   @click="$parent.$emit('grant_bot', props.row)" />
                            <q-btn dense flat color="orange" label="Restart"
                                   @click="$parent.$emit('restart_bot', props.row)" />
                        </div>
                    </q-card>
                </div>
            ''')

            async def _on_edit_bot(e) -> None:
                await _open_bot_edit_dialog(user, bot_table, e.args)

            async def _on_grant_bot(e) -> None:
                await _open_bot_tenants_dialog(user, e.args)

            async def _on_restart_bot(e) -> None:
                await _restart_bot(user, bot_table, e.args)

            bot_table.on('edit_bot', _on_edit_bot)
            bot_table.on('grant_bot', _on_grant_bot)
            bot_table.on('restart_bot', _on_restart_bot)

            await _refresh_bots(bot_table)

            ui.separator().classes('q-my-lg')

            with ui.row().classes('w-full items-center justify-between'):
                ui.label('Feature Groups').classes('section-title')
                ui.button('New group', icon='add', on_click=lambda: _open_group_create_dialog(user, group_table)).props('color=primary')
            ui.label(
                'Named feature bundles (tiers). Assign a tenant to a group from its '
                'Features button; ungrouped tenants fall back to the default group. '
                'Editing a group updates every tenant on it, live.'
            ).classes('text-caption text-grey')

            group_columns = [
                {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
                {'name': 'flags', 'label': 'Features', 'field': 'flags', 'align': 'left'},
                {'name': 'default', 'label': 'Default', 'field': 'default', 'align': 'left'},
                {'name': 'tenants', 'label': 'Tenants', 'field': 'tenants', 'align': 'left'},
                {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
            ]
            group_table = ui.table(columns=group_columns, rows=[], row_key='id').classes(
                'w-full sgl-table').props(':grid="Quasar.Screen.lt.md"')
            group_table.add_slot('body-cell-actions', '''
                <q-td :props="props">
                    <q-btn dense flat color="primary" label="Edit"
                           @click="$parent.$emit('edit_group', props.row)" />
                    <q-btn dense flat color="negative" label="Delete"
                           @click="$parent.$emit('delete_group', props.row)" />
                </q-td>
            ''')
            group_table.add_slot('item', '''
                <div class="q-pa-xs col-xs-12 col-sm-6">
                    <q-card bordered flat class="q-pa-sm sgl-grid-card">
                        <div class="row items-center justify-between no-wrap q-mb-xs">
                            <div class="text-weight-bold">{{ props.row.name }}</div>
                            <q-badge v-if="props.row.default" color="primary" label="Default" />
                        </div>
                        <div class="row q-mb-xs">
                            <div class="col-4 text-grey-7 text-caption">Features</div>
                            <div class="col-8" style="overflow-wrap:anywhere">{{ props.row.flags }}</div>
                        </div>
                        <div class="row q-mb-xs">
                            <div class="col-4 text-grey-7 text-caption">Tenants</div>
                            <div class="col-8">{{ props.row.tenants }}</div>
                        </div>
                        <div class="row justify-end q-gutter-x-sm q-mt-xs">
                            <q-btn dense flat color="primary" label="Edit"
                                   @click="$parent.$emit('edit_group', props.row)" />
                            <q-btn dense flat color="negative" label="Delete"
                                   @click="$parent.$emit('delete_group', props.row)" />
                        </div>
                    </q-card>
                </div>
            ''')

            async def _on_edit_group(e) -> None:
                await _open_group_edit_dialog(user, group_table, e.args)

            async def _on_delete_group(e) -> None:
                await _delete_group(user, group_table, e.args)

            group_table.on('edit_group', _on_edit_group)
            group_table.on('delete_group', _on_delete_group)

            await _refresh_groups(group_table)

            ui.separator().classes('q-my-lg')

            with ui.row().classes('w-full items-center justify-between'):
                ui.label('Service Health').classes('section-title')
            ui.label(
                'Live health of every external dependency. Probed on a cadence '
                '(when the monitor worker is enabled) and on demand below; '
                'transitions into down / credential-warning fire an alert.'
            ).classes('text-caption text-grey')

            from pages.service_health_view import build_refreshable_board
            health = ServiceHealthService()

            async def _snapshot():
                return health.snapshot()

            build_refreshable_board(_snapshot, refresh_loader=health.refresh)


async def _refresh(table) -> None:
    tenants = await TenantService.list_tenants()
    table.rows = [
        {
            'id': t.id, 'name': t.name, 'slug': t.slug,
            'domain': t.domain or '—',
            'guild': str(t.discord_guild_id) if t.discord_guild_id else '—',
            'active': 'yes' if t.is_active else 'no',
            'active_bool': t.is_active,
        }
        for t in tenants
    ]
    table.update()


def _open_create_dialog(actor, table) -> None:
    with ui.dialog() as dialog, ui.card().classes('w-96 gap-2'):
        ui.label('New tenant').classes('text-lg font-semibold')
        name = ui.input('Name').classes('w-full')
        slug = ui.input('Slug').classes('w-full')
        domain = ui.input('Custom domain (optional)').classes('w-full')
        guild = ui.input('Discord guild id (optional)').classes('w-full')
        guild.props('hint="A server may be shared by multiple tenants"')

        async def submit():
            try:
                guild_id = int(guild.value) if (guild.value or '').strip() else None
            except ValueError:
                ui.notify('Guild id must be numeric', color='warning')
                return
            try:
                await TenantService.create_tenant(
                    actor, name=name.value, slug=slug.value,
                    domain=(domain.value or None), discord_guild_id=guild_id,
                )
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Tenant created', color='positive')
            dialog.close()
            await _refresh(table)

        with ui.row().classes('w-full justify-end'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Create', on_click=submit, color='primary')
    dialog.open()


async def _open_edit_dialog(actor, table, row) -> None:
    tenant = await TenantService.get_by_id(row['id'])
    if tenant is None:
        ui.notify('Tenant no longer exists', color='negative')
        return
    with ui.dialog() as dialog, ui.card().classes('w-96 gap-2'):
        ui.label(f"Edit tenant #{tenant.id}").classes('text-lg font-semibold')
        name = ui.input('Name', value=tenant.name).classes('w-full')
        slug = ui.input('Slug', value=tenant.slug).classes('w-full')
        domain = ui.input('Custom domain', value=tenant.domain or '').classes('w-full')
        guild = ui.input('Discord guild id', value=str(tenant.discord_guild_id or '')).classes('w-full')
        guild.props('hint="A server may be shared by multiple tenants"')
        active = ui.switch('Active', value=tenant.is_active)

        async def submit():
            try:
                guild_id = int(guild.value) if (guild.value or '').strip() else None
            except ValueError:
                ui.notify('Guild id must be numeric', color='warning')
                return
            try:
                await TenantService.update_tenant(
                    actor, tenant, name=name.value, slug=slug.value,
                    domain=(domain.value or None), discord_guild_id=guild_id,
                    is_active=active.value,
                )
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Tenant updated', color='positive')
            dialog.close()
            await _refresh(table)

        with ui.row().classes('w-full justify-end'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save', on_click=submit, color='primary')
    dialog.open()


async def _open_tenant_features_dialog(actor, row) -> None:
    """Super-admin: set a tenant's tier (group) and per-feature overrides.

    Availability normally derives from the assigned group (or the default group
    when ungrouped); a per-feature Inherit / Force-on / Force-off override is the
    exception. Effective state is shown per row. Reopen after assigning a group to
    see refreshed effective values.
    """
    tenant_id = row['id']
    service = FeatureFlagService()
    flags = await service.list_for_tenant(actor, tenant_id)
    groups = await service.list_groups(actor)
    tenant = await TenantService.get_by_id(tenant_id)
    current_group_id = tenant.feature_group_id if tenant is not None else None

    async def _assign(group_id) -> None:
        try:
            await service.assign_tenant_group(actor, tenant_id, group_id or None)
        except (ValueError, PermissionError) as e:
            ui.notify(str(e), color='warning')
            return
        ui.notify('Tier assigned — reopen to see updated availability', color='positive')

    async def _override(flag_value: str, choice: str) -> None:
        mapped = {'inherit': None, 'on': True, 'off': False}[choice]
        try:
            await service.set_availability(actor, tenant_id, FeatureFlag(flag_value), mapped)
        except (ValueError, PermissionError) as e:
            ui.notify(str(e), color='warning')
            return
        ui.notify('Updated', color='positive')

    with ui.dialog() as dialog, ui.card().classes('w-[34rem] gap-2'):
        ui.label(f"Features for {row['name']}").classes('text-lg font-semibold')

        group_options = {0: '— None (default fallback) —'}
        for g in groups:
            group_options[g.id] = g.name + (' (default)' if g.is_default else '')
        ui.select(
            options=group_options, value=current_group_id or 0, label='Tier / group',
            on_change=lambda e: _assign(e.value),
        ).classes('w-full')

        ui.separator()
        ui.label('Per-feature overrides (exceptions to the tier)').classes('text-caption text-grey')
        for f in flags:
            tier = 'on' if f['group_available'] else 'off'
            effective = 'live' if f['live'] else ('available' if f['available'] else 'off')
            current = 'inherit' if f['override'] is None else ('on' if f['override'] else 'off')
            with ui.row().classes('items-center justify-between w-full no-wrap'):
                with ui.column().classes('gap-0'):
                    ui.label(f['label'])
                    ui.label(f"tier: {tier} · effective: {effective}").classes('text-caption text-grey')
                ui.select(
                    options={'inherit': f'Inherit ({tier})', 'on': 'Force on', 'off': 'Force off'},
                    value=current,
                    on_change=lambda e, fv=f['flag']: _override(fv, e.value),
                ).props('dense outlined').classes('w-44')
        with ui.row().classes('w-full justify-end'):
            ui.button('Close', on_click=dialog.close).props('flat')
    dialog.open()


async def _refresh_groups(table) -> None:
    groups = await FeatureFlagService().list_groups_with_counts(await _current_actor())
    rows = []
    for g in groups:
        labels = [spec_for(FeatureFlag(k)).label for k in g['flags']]
        rows.append({
            'id': g['id'], 'name': g['name'],
            'flags': ', '.join(labels) or '—',
            'default': 'yes' if g['is_default'] else '',
            'tenants': str(g['tenant_count']),
        })
    table.rows = rows
    table.update()


def _group_form(existing=None):
    """Render the shared group input widgets; returns them for the submit handler."""
    is_edit = existing is not None
    name = ui.input('Name', value=existing['name'] if is_edit else '').classes('w-full')
    description = ui.textarea(
        'Description', value=existing.get('description', '') if is_edit else '',
    ).classes('w-full')
    flag_options = {spec.flag.value: spec.label for spec in all_specs()}
    flags = ui.select(
        options=flag_options, multiple=True, label='Features in this group',
        value=list(existing['flags']) if is_edit else [],
    ).props('use-chips').classes('w-full')
    is_default = ui.switch('Default group (fallback for ungrouped tenants)',
                           value=existing['is_default'] if is_edit else False)
    return name, description, flags, is_default


def _open_group_create_dialog(actor, table) -> None:
    with ui.dialog() as dialog, ui.card().classes('w-[32rem] gap-2'):
        ui.label('New feature group').classes('text-lg font-semibold')
        name, description, flags, is_default = _group_form()

        async def submit():
            try:
                await FeatureFlagService().create_group(
                    actor, name=name.value, flags=flags.value or [],
                    description=description.value, is_default=is_default.value,
                )
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Group created', color='positive')
            dialog.close()
            await _refresh_groups(table)

        with ui.row().classes('w-full justify-end'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Create', on_click=submit, color='primary')
    dialog.open()


async def _open_group_edit_dialog(actor, table, row) -> None:
    group = await FeatureFlagService().get_group(actor, row['id'])
    existing = {
        'name': group.name, 'description': group.description or '',
        'flags': list(group.flags or []), 'is_default': group.is_default,
    }
    with ui.dialog() as dialog, ui.card().classes('w-[32rem] gap-2'):
        ui.label(f"Edit group '{group.name}'").classes('text-lg font-semibold')
        name, description, flags, is_default = _group_form(existing)

        async def submit():
            try:
                await FeatureFlagService().update_group(
                    actor, group.id, name=name.value, flags=flags.value or [],
                    description=description.value, is_default=is_default.value,
                )
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Group updated', color='positive')
            dialog.close()
            await _refresh_groups(table)

        with ui.row().classes('w-full justify-end'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save', on_click=submit, color='primary')
    dialog.open()


async def _delete_group(actor, table, row) -> None:
    try:
        await FeatureFlagService().delete_group(actor, row['id'])
    except (ValueError, PermissionError) as e:
        ui.notify(str(e), color='warning')
        return
    ui.notify('Group deleted; its tenants fell back to the default', color='positive')
    await _refresh_groups(table)


async def _refresh_bots(table) -> None:
    bots = await _bot_service.list_bots(await _current_actor())
    table.rows = [
        {
            'id': b.id, 'category': b.category, 'name': b.name,
            'client_id': b.client_id,
            'active': 'yes' if b.is_active else 'no',
            'active_bool': b.is_active,
            # Humanized status ('connected' -> 'Connected'), never the raw
            # 'BotStatus.CONNECTED' repr; message appended when present.
            'status': (
                f'{b.status.value.title()} — {b.status_message}'
                if b.status_message else b.status.value.title()
            ),
            'status_kind': b.status.value,
        }
        for b in bots
    ]
    table.update()


async def _restart_bot(actor, table, row) -> None:
    from racetimebot import get_racetime_manager
    try:
        await get_racetime_manager().restart(actor, row['id'])
    except (ValueError, PermissionError) as e:
        ui.notify(str(e), color='warning')
        return
    ui.notify('Bot connection restarting', color='positive')
    await _refresh_bots(table)


async def _current_actor():
    return await get_user_from_discord_id(app.storage.user.get('discord_id'))


def _bot_form(existing=None):
    """Render the shared bot input widgets; returns them for the submit handler."""
    is_edit = existing is not None
    category = ui.input('Category', value=existing['category'] if is_edit else '').classes('w-full')
    name = ui.input('Name', value=existing['name'] if is_edit else '').classes('w-full')
    client_id = ui.input('Client ID', value=existing['client_id'] if is_edit else '').classes('w-full')
    secret = ui.input('Client Secret').props('type=password').classes('w-full')
    if is_edit:
        secret.props('hint="Leave blank to keep the current secret"')
    description = ui.textarea('Description', value=existing.get('description', '') if is_edit else '').classes('w-full')
    handler = ui.input('Handler class', value=existing.get('handler_class', '') if is_edit else '').classes('w-full')
    active = ui.switch('Active', value=existing['active'] == 'yes' if is_edit else True)
    return category, name, client_id, secret, description, handler, active


def _open_bot_create_dialog(actor, table) -> None:
    with ui.dialog() as dialog, ui.card().classes('w-96 gap-2'):
        ui.label('New racetime bot').classes('text-lg font-semibold')
        category, name, client_id, secret, description, handler, active = _bot_form()

        async def submit():
            try:
                await _bot_service.create_bot(
                    actor, category=category.value, name=name.value,
                    client_id=client_id.value, client_secret=secret.value,
                    description=description.value, handler_class=handler.value,
                    is_active=active.value,
                )
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Bot created', color='positive')
            dialog.close()
            await _refresh_bots(table)

        with ui.row().classes('w-full justify-end'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Create', on_click=submit, color='primary')
    dialog.open()


async def _open_bot_edit_dialog(actor, table, row) -> None:
    bot = await _bot_service.get_bot(actor, row['id'])
    existing = _bot_service.serialize(bot)
    with ui.dialog() as dialog, ui.card().classes('w-96 gap-2'):
        ui.label(f"Edit bot #{bot.id}").classes('text-lg font-semibold')
        # serialize() omits the secret; expose the plain fields to the form.
        existing['active'] = 'yes' if bot.is_active else 'no'
        category, name, client_id, secret, description, handler, active = _bot_form(existing)

        async def submit():
            try:
                await _bot_service.update_bot(
                    actor, bot.id, category=category.value, name=name.value,
                    client_id=client_id.value, client_secret=secret.value,
                    description=description.value, handler_class=handler.value,
                    is_active=active.value,
                )
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Bot updated', color='positive')
            dialog.close()
            await _refresh_bots(table)

        async def delete_bot():
            try:
                await _bot_service.delete_bot(actor, bot.id)
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Bot deleted', color='positive')
            dialog.close()
            await _refresh_bots(table)

        with ui.row().classes('w-full justify-between'):
            ui.button('Delete', on_click=delete_bot, color='negative').props('flat')
            with ui.row():
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save', on_click=submit, color='primary')
    dialog.open()


async def _open_bot_tenants_dialog(actor, row) -> None:
    bot_id = row['id']
    tenants = await TenantService.list_tenants()
    grants = {g.tenant_id: g for g in await _bot_service.list_grants(actor, bot_id)}
    with ui.dialog() as dialog, ui.card().classes('w-96 gap-2'):
        ui.label(f"Tenants for {row['category']}").classes('text-lg font-semibold')
        ui.label('Toggle which tenants may select this bot.').classes('text-caption text-grey')

        async def _toggle(tenant_id: int, enabled: bool):
            try:
                if enabled:
                    await _bot_service.grant_tenant(actor, bot_id, tenant_id)
                else:
                    await _bot_service.revoke_tenant(actor, bot_id, tenant_id)
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Updated', color='positive')

        for t in tenants:
            grant = grants.get(t.id)
            ui.switch(
                t.name, value=bool(grant and grant.is_active),
                on_change=lambda e, tid=t.id: _toggle(tid, e.value),
            )

        with ui.row().classes('w-full justify-end'):
            ui.button('Close', on_click=dialog.close).props('flat')
    dialog.open()
