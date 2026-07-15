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
from application.tenant_context import get_current_tenant_id
from models import FeatureFlag

_bot_service = RacetimeBotService()


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
        with ui.column().classes('w-full max-w-5xl mx-auto p-6 gap-4'):
            with ui.row().classes('w-full items-center justify-between'):
                ui.label('Platform Administration').classes('text-2xl font-bold')
                ui.button('New tenant', icon='add', on_click=lambda: _open_create_dialog(user, table))

            columns = [
                {'name': 'id', 'label': 'ID', 'field': 'id', 'align': 'left'},
                {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
                {'name': 'slug', 'label': 'Slug (/t/…)', 'field': 'slug', 'align': 'left'},
                {'name': 'domain', 'label': 'Domain', 'field': 'domain', 'align': 'left'},
                {'name': 'guild', 'label': 'Guild', 'field': 'guild', 'align': 'left'},
                {'name': 'active', 'label': 'Active', 'field': 'active', 'align': 'left'},
                {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
            ]
            table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full')
            table.add_slot('body-cell-actions', '''
                <q-td :props="props">
                    <q-btn dense flat color="primary" label="Edit"
                           @click="$parent.$emit('edit', props.row)" />
                    <q-btn dense flat color="secondary" label="Features"
                           @click="$parent.$emit('features', props.row)" />
                </q-td>
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
                ui.label('Racetime Bots').classes('text-2xl font-bold')
                ui.button('New bot', icon='add', on_click=lambda: _open_bot_create_dialog(user, bot_table))
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
            bot_table = ui.table(columns=bot_columns, rows=[], row_key='id').classes('w-full')
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
                ui.label('Service Health').classes('text-2xl font-bold')
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
    """Super-admin tier: grant which features a tenant *may* use.

    Toggling ``available`` here is the platform grant; the tenant's STAFF then
    enable a granted feature in Admin → Features. Effective (what users see) is
    available AND enabled, shown per row.
    """
    tenant_id = row['id']
    service = FeatureFlagService()
    flags = await service.list_for_tenant(actor, tenant_id)

    async def _toggle(flag_value: str, available: bool) -> None:
        try:
            await service.set_availability(actor, tenant_id, FeatureFlag(flag_value), available)
        except (ValueError, PermissionError) as e:
            ui.notify(str(e), color='warning')
            return
        ui.notify('Updated', color='positive')

    with ui.dialog() as dialog, ui.card().classes('w-96 gap-2'):
        ui.label(f"Features for {row['name']}").classes('text-lg font-semibold')
        ui.label(
            'Grant which features this community may use. Its staff then enable '
            'the granted ones in Admin → Features.'
        ).classes('text-caption text-grey')
        for f in flags:
            with ui.row().classes('items-center justify-between w-full no-wrap'):
                with ui.column().classes('gap-0'):
                    ui.label(f['label'])
                    if f['available'] and f['enabled']:
                        status = 'Live (tenant has it on)'
                    elif f['available']:
                        status = 'Available (tenant has it off)'
                    else:
                        status = 'Not available'
                    ui.label(status).classes('text-caption text-grey')
                ui.switch(
                    value=f['available'],
                    on_change=lambda e, fv=f['flag']: _toggle(fv, e.value),
                ).props('color=primary')
        with ui.row().classes('w-full justify-end'):
            ui.button('Close', on_click=dialog.close).props('flat')
    dialog.open()


async def _refresh_bots(table) -> None:
    bots = await _bot_service.list_bots(await _current_actor())
    table.rows = [
        {
            'id': b.id, 'category': b.category, 'name': b.name,
            'client_id': b.client_id,
            'active': 'yes' if b.is_active else 'no',
            'status': (f'{b.status} — {b.status_message}' if b.status_message else b.status),
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
