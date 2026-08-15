"""Platform (super-admin) surface at ``/platform``.

Served on the bare platform host with **no** tenant context and gated to the
global ``SUPER_ADMIN`` role. Manages tenant CRUD (name, slug, domain, guild id,
active). Runs tenant-agnostically — its queries pass explicit ids, so the
per-tenant scoping never applies.

The page stacks four sections; this module owns the tenants table and stacks the
rest from their own modules, which is what keeps it inside the file-length
guideline: :mod:`pages.platform_bots` (racetime bots),
:mod:`pages.platform_feature_groups` (tiers, and one tenant's overrides),
:mod:`pages.platform_tenant_admins` (a community's first staff member) and
:mod:`pages.service_health_view` (the health board, shared with the admin tab).
"""

from nicegui import app, ui

from application.services import (
    RacetimeBotService,
    ServiceHealthService,
    TablePreferenceService,
    TenantService,
    TenantSetupService,
    get_user_from_discord_id,
)
from application.services.auth_service import AuthService
from application.table_preferences_context import table_prefs_scope
from application.tenant_context import get_current_tenant_id
from pages.platform_bots import render_bots_section
from pages.platform_feature_groups import (
    open_tenant_features_dialog,
    render_feature_groups_section,
)
from pages.platform_shared import ACTIVE_ICON_SLOT
from pages.platform_tenant_admins import open_tenant_admins_dialog
from theme.chrome import render_platform_chrome
from theme.notify import notify_error
from theme.tables.preferences import (
    TableKeys,
    customize_table,
    preferences_button,
    search_input,
)

_bot_service = RacetimeBotService()

# Shared active-column icon slot (check_circle / cancel), matching the styled
# admin tables. Rows must carry an ``active_bool`` boolean.

# Readiness chip, shared by the desktop Setup cell and the mobile card. Rows must
# carry ``setup`` (text), ``setup_ready`` and ``setup_missing`` (tooltip).
_SETUP_CHIP = '''
    <span class="wiz-chip" :class="props.row.setup_ready ? 'wiz-chip--ok' : 'wiz-chip--neutral'">
        {{ props.row.setup }}
        <q-tooltip>{{ props.row.setup_missing }}</q-tooltip>
    </span>
'''



def _render_platform_chrome() -> None:
    """Phoenix brand chrome for the standalone platform surface.

    /platform runs on the bare host with no tenant, so it can't reuse the
    tenant BaseLayout (whose drawer links into /admin, /volunteer). It shares
    :func:`~theme.chrome.render_platform_chrome` with the other tenant-less
    surfaces and adds a link back to the community picker.
    """
    def _communities_link() -> None:
        with ui.link(target='/').classes('no-underline'):
            with ui.row().classes('items-center no-wrap wiz-header-link'):
                ui.icon('arrow_back').props('size=sm')
                ui.label('Communities')

    render_platform_chrome('Platform', right=_communities_link)


def create() -> None:
    @ui.page('/platform')
    async def platform() -> None:
        from theme.error_page import render_error_page

        # /platform is a platform-level page: reached via /t/<slug>/platform it
        # would carry a tenant — that is not a tenant page, so 404.
        if get_current_tenant_id() is not None:
            render_error_page(
                status_code=404, headline='Not Found',
                message="Platform administration isn't available from this address.", user=None,
            )
            return

        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        if not await AuthService.is_super_admin(user):
            render_error_page(
                status_code=403, headline='Forbidden',
                message="You'll need super-admin access for this page.", user=user,
            )
            return

        ui.page_title('Platform Administration')
        _render_platform_chrome()
        # This surface builds its own chrome rather than BaseLayout, so it primes
        # the viewer's table layouts itself — without this the gears below would
        # save preferences that never came back.
        prefs = await TablePreferenceService().prime(user)
        with table_prefs_scope(prefs), \
                ui.column().classes('w-full max-w-5xl mx-auto p-6 gap-4'):
            with ui.row().classes('w-full items-center justify-between'):
                ui.label('Platform Administration').classes('page-title')
                with ui.row().classes('items-center gap-2'):
                    # Filled once the table exists; the header is drawn first.
                    header_row = ui.row().classes('items-center')
                    ui.button('New tenant', icon='add', on_click=lambda: _open_create_dialog(user, table)).props('color=primary')

            columns: list[dict] = [
                {'name': 'id', 'label': 'ID', 'field': 'id', 'align': 'left'},
                {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
                {'name': 'slug', 'label': 'Slug (/t/…)', 'field': 'slug', 'align': 'left'},
                {'name': 'domain', 'label': 'Domain', 'field': 'domain', 'align': 'left'},
                {'name': 'guild', 'label': 'Guild', 'field': 'guild', 'align': 'left'},
                {'name': 'active', 'label': 'Active', 'field': 'active', 'align': 'left'},
                {'name': 'setup', 'label': 'Setup', 'field': 'setup', 'align': 'left'},
                {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
            ]
            table = ui.table(columns=columns, rows=[], row_key='id').classes(
                'w-full wiz-table').props(':grid="Quasar.Screen.lt.md"')
            table.add_slot('body-cell-active', ACTIVE_ICON_SLOT)
            table.add_slot('body-cell-setup', f'<q-td :props="props">{_SETUP_CHIP}</q-td>')
            # Icon actions, not labels: a third action pushed the labelled row
            # past the card width and clipped it. The mobile card below has room
            # and keeps the words.
            table.add_slot('body-cell-actions', '''
                <q-td :props="props">
                    <q-btn dense flat round icon="edit" color="primary"
                           @click="$parent.$emit('edit', props.row)"><q-tooltip>Edit</q-tooltip></q-btn>
                    <q-btn dense flat round icon="toggle_on" color="secondary"
                           @click="$parent.$emit('features', props.row)"><q-tooltip>Features</q-tooltip></q-btn>
                    <q-btn dense flat round icon="shield" color="accent"
                           @click="$parent.$emit('admins', props.row)"><q-tooltip>Admins</q-tooltip></q-btn>
                </q-td>
            ''')
            table.add_slot('item', '''
                <div class="q-pa-xs col-xs-12 col-sm-6">
                    <q-card bordered flat class="q-pa-sm wiz-grid-card">
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
                        <div class="row items-center q-mb-xs">
                            <div class="col-4 text-grey-7 text-caption">Setup</div>
                            <div class="col-8">''' + _SETUP_CHIP + '''</div>
                        </div>
                        <div class="row justify-end q-gutter-x-sm q-mt-xs">
                            <q-btn dense flat color="primary" label="Edit"
                                   @click="$parent.$emit('edit', props.row)" />
                            <q-btn dense flat color="secondary" label="Features"
                                   @click="$parent.$emit('features', props.row)" />
                            <q-btn dense flat color="accent" label="Admins"
                                   @click="$parent.$emit('admins', props.row)" />
                        </div>
                    </q-card>
                </div>
            ''')

            customize_table(table, columns, key=TableKeys.PLATFORM_TENANTS)
            with header_row:
                search_input(table, placeholder='Search communities…')
                preferences_button(table)

            async def _on_edit(e) -> None:
                # Awaited by NiceGUI within the client's slot context (not a
                # background task), so ui.* calls in the dialog are safe.
                await _open_edit_dialog(user, table, e.args)

            async def _on_features(e) -> None:
                await open_tenant_features_dialog(user, e.args)

            async def _on_admins(e) -> None:
                await open_tenant_admins_dialog(user, e.args['id'], e.args['name'])

            table.on('edit', _on_edit)
            table.on('features', _on_features)
            table.on('admins', _on_admins)

            await _refresh(table)

            ui.separator().classes('q-my-lg')

            await render_bots_section(user)

            ui.separator().classes('q-my-lg')

            await render_feature_groups_section(user)

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
    rows = []
    for t in tenants:
        # Five existence checks per tenant, so N×5 queries. Deliberate: /platform
        # is super-admin-only, lists tens of tenants and is not a hot path, and
        # this is simpler than a bespoke aggregate. Past a few hundred tenants
        # the fix is one grouped query in TenantSetupService, not caching here.
        steps = await TenantSetupService.status_for(t.id)
        outstanding = TenantSetupService.outstanding(steps)
        required = sum(1 for s in steps if s.required)
        rows.append({
            'id': t.id, 'name': t.name, 'slug': t.slug,
            'domain': t.domain or '—',
            'guild': str(t.discord_guild_id) if t.discord_guild_id else '—',
            'active': 'yes' if t.is_active else 'no',
            'active_bool': t.is_active,
            'setup': (
                'Ready' if not outstanding
                else f'{required - len(outstanding)} of {required}'
            ),
            'setup_ready': not outstanding,
            'setup_missing': ', '.join(s.label for s in outstanding) or 'Nothing outstanding',
        })
    table.rows = rows
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
                tenant = await TenantService.create_tenant(
                    actor, name=name.value, slug=slug.value,
                    domain=(domain.value or None), discord_guild_id=guild_id,
                )
            except (ValueError, PermissionError) as e:
                notify_error(e)
                return
            ui.notify('Tenant created', color='positive')
            dialog.close()
            await _refresh(table)
            # A community with no staff cannot be administered, so ask who runs
            # it now rather than leaving the super-admin to find the Admins row
            # action on their own.
            await open_tenant_admins_dialog(actor, tenant.id, tenant.name)

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
                notify_error(e)
                return
            ui.notify('Tenant updated', color='positive')
            dialog.close()
            await _refresh(table)

        with ui.row().classes('w-full justify-end'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save', on_click=submit, color='primary')
    dialog.open()



