"""Admin Discord Role Mapping Page"""

from nicegui import background_tasks, ui

from application.services import (
    AuthService,
    DiscordRoleMappingService,
    DiscordService,
    SystemConfigService,
    current_user_from_storage,
)
from models import Role


_ROLE_OPTIONS = {r.value: r.value.replace('_', ' ').title() for r in Role}


async def admin_discord_roles_page() -> None:
    actor = await current_user_from_storage()
    can_manage = await AuthService.can_grant_roles(actor)

    service = DiscordRoleMappingService()
    guild_id = await SystemConfigService.get_discord_sync_guild_id()

    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('Discord Role Mapping').classes('page-title')

        ui.separator().classes('separator-spacing')

        if not guild_id:
            ui.label(
                'No Discord server is configured for role sync. '
                'Choose one under the Settings tab first.'
            ).classes('text-grey')
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

        async def delete_mapping(row):
            try:
                current = await current_user_from_storage()
                await service.remove_mapping(row['id'], current)
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Mapping removed', color='positive')
            await refresh_table()

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
                            current = await current_user_from_storage()
                            await service.add_mapping(
                                guild_id=guild_id,
                                discord_role_id=int(discord_select.value),
                                discord_role_name=role_options[int(discord_select.value)],
                                app_role=Role(app_select.value),
                                actor=current,
                            )
                        except (ValueError, PermissionError) as e:
                            ui.notify(str(e), color='warning')
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
                ui.space()
                ui.button(
                    icon='refresh', on_click=lambda: background_tasks.create(refresh_table()),
                ).props('flat color=primary').tooltip('Refresh table')

            table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full')

            table.add_slot('body-cell-actions', '''
                <q-td :props="props">
                    <q-btn flat round dense icon="delete" color="negative"
                           @click="$parent.$emit('delete', props.row)">
                        <q-tooltip>Remove mapping</q-tooltip>
                    </q-btn>
                </q-td>
            ''')

            table.on('delete', lambda e: background_tasks.create(delete_mapping(e.args)))

        ui.on('selected_tab', lambda e: background_tasks.create(refresh_table()) if e.args == 'Discord Roles' else None)
        background_tasks.create(refresh_table())
