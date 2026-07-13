"""Platform (super-admin) surface at ``/platform``.

Served on the bare platform host with **no** tenant context and gated to the
global ``SUPER_ADMIN`` role. Manages tenant CRUD (name, slug, domain, guild id,
active). Runs tenant-agnostically — its queries pass explicit ids, so the
per-tenant scoping never applies.
"""

from nicegui import app, ui

from application.services import TenantService, get_user_from_discord_id
from application.services.auth_service import AuthService
from application.tenant_context import get_current_tenant_id


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
                </q-td>
            ''')

            async def _on_edit(e) -> None:
                # Awaited by NiceGUI within the client's slot context (not a
                # background task), so ui.* calls in the dialog are safe.
                await _open_edit_dialog(user, table, e.args)

            table.on('edit', _on_edit)

            await _refresh(table)


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
