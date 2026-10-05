"""Volunteer-position role mappings: the second half of the Role Mappings tab."""

from nicegui import app, background_tasks, context, ui

from application.services import (
    VolunteerPositionService,
    VolunteerRoleMappingService,
    get_user_from_discord_id,
)
from models import Role
from theme.dialog._helpers import dialog_actions, form_dialog
from theme.notify import notify_error
from theme.tables.admin_crud import refresh_button, wire_tab_refresh
from theme.tables.mobile_grid import enable_mobile_grid
from theme.tables.preferences import TableKeys

TAB_LABEL = 'Role Mappings'

_ROLE_OPTIONS = {
    r.value: r.value.replace('_', ' ').title() for r in Role.volunteer_mappable()
}

_ROW_ACTIONS = '''
    <q-btn flat round dense icon="delete" color="negative"
           @click="$parent.$emit('delete', props.row)">
        <q-tooltip>Remove mapping</q-tooltip>
    </q-btn>
'''


async def volunteer_role_mappings_section(can_manage: bool) -> None:
    service = VolunteerRoleMappingService()

    ui.label('Volunteer positions').classes('subsection-title')
    ui.label(
        "Anyone with a published assignment to a shift of the position holds the "
        "role, and keeps it while any such assignment exists, finished shifts "
        "included. Unpublished drafts don't count. Unassigning, releasing, or "
        "deleting the shift or position takes it back; manually-granted roles "
        "are never touched."
    ).classes('text-caption text-grey')
    ui.label(
        "Coordinators decide who's on a shift, so only operational roles can be "
        "mapped: never Staff or a role that runs a subsystem."
    ).classes('text-caption text-grey')

    columns = [
        {'name': 'id', 'label': 'ID', 'field': 'id', 'hidden': True},
        {'name': 'position', 'label': 'Position', 'field': 'position', 'sortable': True},
        {'name': 'app_role', 'label': 'Grants', 'field': 'app_role', 'sortable': True},
        {'name': 'actions', 'label': '', 'field': 'actions'},
    ]
    container = ui.column().classes('w-full')

    async def refresh_table() -> None:
        try:
            mappings = await service.list_mappings()
        except ValueError as e:
            notify_error(e)
            return
        table.rows = [
            {
                'id': m.id,
                'position': m.position.name,
                'app_role': _ROLE_OPTIONS.get(m.app_role.value, m.app_role.value),
            }
            for m in mappings
        ]
        table.update()

    async def open_add_dialog() -> None:
        positions = await VolunteerPositionService().list_all()
        if not positions:
            ui.notify(
                'No volunteer positions yet. Add one under Vol. Schedule → Manage positions.',
                color='warning',
            )
            return
        position_options = {p.id: p.name for p in positions}

        with container, form_dialog('Add volunteer role mapping') as dialog:
            with ui.column().classes('q-pa-md gap-2 full-width'):
                position_select = ui.select(
                    options=position_options, label='Position', with_input=True,
                ).classes('w-full')
                role_select = ui.select(options=_ROLE_OPTIONS, label='Grants').classes('w-full')

            async def submit() -> None:
                if position_select.value is None or not role_select.value:
                    ui.notify('Pick a position and the role it grants.', color='warning')
                    return
                try:
                    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                    await service.add_mapping(
                        actor, int(position_select.value), Role(role_select.value),
                    )
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                dialog.close()
                ui.notify('Mapping added', color='positive')
                await refresh_table()

            with dialog_actions().classes('justify-end'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Add', icon='add', on_click=submit).props('color=primary')
        dialog.open()

    async def delete_mapping(row: dict, client) -> None:
        with client:
            try:
                actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                await service.remove_mapping(actor, row['id'])
            except (ValueError, PermissionError) as e:
                notify_error(e)
                return
            ui.notify('Mapping removed', color='positive')
            await refresh_table()

    with container:
        with ui.row().classes('full-width'):
            if can_manage:
                ui.button('Add Mapping', icon='add', on_click=open_add_dialog).props('color=primary')
            ui.space()
            refresh_button(refresh_table)

        table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full wiz-table')
        if can_manage:
            table.add_slot('body-cell-actions', f'<q-td :props="props">{_ROW_ACTIONS}</q-td>')
        table.on('delete', lambda e: background_tasks.create(delete_mapping(e.args, context.client)))
        enable_mobile_grid(
            table, columns, actions=_ROW_ACTIONS if can_manage else '',
            table_key=TableKeys.ADMIN_VOLUNTEER_ROLE_MAPPINGS,
        )

    wire_tab_refresh(TAB_LABEL, refresh_table)
    background_tasks.create(refresh_table())
