"""Admin Discord Role Mapping Page"""

import secrets
from urllib.parse import quote

from nicegui import app, background_tasks, context, ui
from theme.notify import notify_error
from theme.tables.admin_crud import wire_tab_refresh
from theme.tables.mobile_grid import enable_mobile_grid

from application.services import (
    AuthService,
    DiscordLinkService,
    DiscordRoleMappingService,
    DiscordService,
    TenantService,
    get_user_from_discord_id,
)
from application.services.discord_link_service import connect_redirect_uri
from application.tenant_context import get_current_tenant_id, is_host_mode
from application.utils.mock_discord import is_mock_discord
from models import Role


_ROLE_OPTIONS = {r.value: r.value.replace('_', ' ').title() for r in Role}

_ROW_ACTIONS = '''
    <q-btn flat round dense icon="delete" color="negative"
           @click="$parent.$emit('delete', props.row)">
        <q-tooltip>Remove mapping</q-tooltip>
    </q-btn>
'''


async def admin_discord_roles_page() -> None:
    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    can_manage = await AuthService.can_grant_roles(actor)

    service = DiscordRoleMappingService()
    tenant_id = get_current_tenant_id()
    tenant = await TenantService.get_by_id(tenant_id) if tenant_id else None
    guild_id = tenant.discord_guild_id if tenant else None
    admin_path = f'/t/{tenant.slug}/admin' if tenant else '/admin'

    # Resolve the connected server's name (best-effort; the bot may be starting).
    server_name = None
    if guild_id:
        ok, summary = await DiscordService().get_guild_summary(guild_id)
        if ok and isinstance(summary, dict):
            server_name = str(summary.get('name'))

    async def connect_server():
        if is_host_mode():
            # The connect callback is registered on the platform host; it can't
            # see this custom domain's session cookie, so complete it there.
            ui.notify(
                'Connect Discord from the main site (…/t/<slug>/admin), not this custom domain.',
                color='warning',
            )
            return
        if not await DiscordLinkService.can_manage_link(actor):
            ui.notify('You need the Staff role to connect a Discord server.', color='warning')
            return
        if tenant is None:
            ui.notify('No community is in scope.', color='warning')
            return
        # Carry the target tenant, CSRF state, and return path across the redirect
        # — the callback lands on the bare platform host with no tenant in scope.
        state = secrets.token_urlsafe(32)
        app.storage.user['discord_connect_state'] = state
        app.storage.user['discord_connect_tenant_id'] = tenant.id
        app.storage.user['discord_connect_return'] = admin_path
        if is_mock_discord():
            # Dev: skip real Discord and hand a mock guild straight to the callback.
            target = f'{connect_redirect_uri()}?state={quote(state)}&guild_id=1'
        else:
            target = DiscordLinkService.authorize_url(state)
        ui.navigate.to(target)

    async def disconnect_server(client):
        with client:
            try:
                current = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                if tenant is None:
                    ui.notify('No community is in scope.', color='warning')
                    return
                await DiscordLinkService.disconnect(current, tenant)
            except (ValueError, PermissionError) as e:
                notify_error(e)
                return
            ui.notify('Discord server disconnected.', color='positive')
            ui.navigate.to(admin_path)

    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('Discord Role Mapping').classes('page-title')

        ui.separator().classes('separator-spacing')

        # --- Server connection ---
        with ui.card().classes('w-full'):
            if guild_id:
                label = server_name or f'Guild {guild_id}'
                with ui.row().classes('items-center gap-2'):
                    ui.icon('check_circle', color='positive')
                    ui.label(f'Connected to {label}').classes('text-bold')
                if not server_name:
                    ui.label(
                        'The bot is linked but not currently reachable in this server. '
                        'Role sync resumes once the bot is back online in it.'
                    ).classes('text-caption text-warning')
                if can_manage:
                    ui.button(
                        'Disconnect', icon='link_off',
                        on_click=lambda: background_tasks.create(disconnect_server(context.client)),
                    ).props('outline color=negative')
            else:
                ui.label('No Discord server is connected to this community.').classes('text-bold')
                ui.label(
                    'Connecting opens Discord and adds the bot to a server you manage. '
                    'You must have the "Manage Server" permission on that server.'
                ).classes('text-caption text-grey')
                if can_manage and is_host_mode():
                    ui.label(
                        'Connect a Discord server from the main site (…/t/<slug>/admin); '
                        'this step is unavailable on a custom domain.'
                    ).classes('text-caption text-warning')
                elif can_manage:
                    ui.button(
                        'Connect Discord server', icon='hub', on_click=connect_server,
                    ).props('color=primary')

        if not guild_id:
            return

        ui.label(
            'When a user signs in, app roles are granted or revoked to match their '
            'Discord roles against these mappings. Manually-granted roles are preserved.'
        ).classes('text-caption text-grey')

        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id', 'hidden': True},
            {'name': 'discord_role_name', 'label': 'Discord Role', 'field': 'discord_role_name', 'sortable': True},
            {'name': 'app_role', 'label': 'App Role', 'field': 'app_role', 'sortable': True},
            {'name': 'actions', 'label': '', 'field': 'actions'},
        ]

        table_container = ui.column().classes('w-full')

        async def refresh_table():
            mappings = await service.list_mappings(guild_id)
            table.rows = [
                {
                    'id': m.id,
                    'discord_role_name': m.discord_role_name,
                    'app_role': _ROLE_OPTIONS.get(m.app_role.value, m.app_role.value),
                }
                for m in mappings
            ]
            table.update()

        async def delete_mapping(row, client):
            with client:
                try:
                    current = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                    await service.remove_mapping(row['id'], current)
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify('Mapping removed', color='positive')
                await refresh_table()

        async def sync_all_users(client):
            with client:
                with ui.dialog() as confirm, ui.card():
                    ui.label(
                        'Re-sync Discord roles for all users now? This applies the '
                        'current mappings immediately and may take a moment.'
                    )
                    with ui.row().classes('justify-end w-full'):
                        ui.button('Cancel', on_click=lambda: confirm.submit(False)).props('flat')
                        ui.button('Sync', icon='sync', on_click=lambda: confirm.submit(True)).props('color=primary')
                if not await confirm:
                    return
                ui.notify('Syncing Discord roles for all users…')
                try:
                    current = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                    result = await service.sync_all_users(current)
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify(
                    f"Synced {result['users_processed']} users: "
                    f"{result['granted']} granted, {result['revoked']} revoked",
                    color='positive',
                )

        async def open_add_dialog():
            ok, roles_payload = await DiscordService().list_guild_roles(guild_id)
            if not ok:
                ui.notify(str(roles_payload), color='warning')
                return
            role_options = {int(r['id']): str(r['name']) for r in roles_payload}

            with table_container:
                with ui.dialog() as dialog, ui.card().classes('w-96'):
                    ui.label('Add Role Mapping').classes('text-h6')
                    discord_select = ui.select(
                        options=role_options, label='Discord Role', with_input=True,
                    ).classes('w-full')
                    app_select = ui.select(
                        options=_ROLE_OPTIONS, label='Application Role',
                    ).classes('w-full')

                    async def submit():
                        if discord_select.value is None or not app_select.value:
                            ui.notify('Select both a Discord role and an application role.', color='warning')
                            return
                        try:
                            current = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                            await service.add_mapping(
                                guild_id=guild_id,
                                discord_role_id=int(discord_select.value),
                                discord_role_name=role_options[int(discord_select.value)],
                                app_role=Role(app_select.value),
                                actor=current,
                            )
                        except (ValueError, PermissionError) as e:
                            notify_error(e)
                            return
                        dialog.close()
                        ui.notify('Mapping added', color='positive')
                        await refresh_table()

                    with ui.row().classes('justify-end w-full'):
                        ui.button('Cancel', on_click=dialog.close).props('flat')
                        ui.button('Add', icon='add', on_click=submit).props('color=primary')
            dialog.open()

        with table_container:
            with ui.row().classes('full-width'):
                if can_manage:
                    ui.button('Add Mapping', icon='add', on_click=open_add_dialog).props('color=primary')
                    ui.button(
                        'Sync All Users', icon='sync',
                        on_click=lambda: background_tasks.create(sync_all_users(context.client)),
                    ).props('outline color=primary').tooltip(
                        'Apply current mappings to all users now'
                    )
                ui.space()
                ui.button(
                    icon='refresh', on_click=lambda: background_tasks.create(refresh_table()),
                ).props('flat color=primary').tooltip('Refresh table')

            table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full wiz-table')

            table.add_slot('body-cell-actions', f'<q-td :props="props">{_ROW_ACTIONS}</q-td>')

            table.on('delete', lambda e: background_tasks.create(delete_mapping(e.args, context.client)))

            enable_mobile_grid(table, columns, actions=_ROW_ACTIONS)

        wire_tab_refresh('Discord Roles', refresh_table)
        background_tasks.create(refresh_table())
