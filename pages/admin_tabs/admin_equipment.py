"""Admin Equipment Management Page (Equipment Manager / Staff)."""

from nicegui import app, background_tasks, context, ui
from theme.notify import notify_error

from application.services import EquipmentService, get_user_from_discord_id
from theme.dialog import ConfirmationDialog, EquipmentDialog, open_checkout, quick_checkin

_STATUS_LABELS = {
    'available': 'Available',
    'checked_out': 'Checked out',
    'retired': 'Retired',
}

_COLUMNS = [
    {'name': 'asset_number', 'label': '#', 'field': 'asset_number', 'align': 'left', 'sortable': True},
    {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
    {'name': 'owner', 'label': 'Owner', 'field': 'owner', 'align': 'left'},
    {'name': 'status', 'label': 'Status', 'field': 'status', 'align': 'left', 'sortable': True},
    {'name': 'holder', 'label': 'Checked out to', 'field': 'holder', 'align': 'left'},
    {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
]


async def admin_equipment_page() -> None:
    service = EquipmentService()

    with ui.column().classes('page-container-narrow w-full'):
        with ui.row().classes('header-row'):
            ui.label('Equipment').classes('page-title')

        ui.separator().classes('separator-spacing')

        with ui.row().classes('full-width items-center'):
            async def add_asset():
                actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                await EquipmentDialog(actor, on_saved=_render_table.refresh).open()

            ui.button('Add Asset', icon='add', on_click=add_asset).props('color=primary')
            ui.space()
            ui.button(
                icon='refresh',
                on_click=lambda: background_tasks.create(_render_table.refresh()),
            ).props('flat color=primary').tooltip('Refresh')

        @ui.refreshable
        async def _render_table() -> None:
            assets = await service.list_assets()
            open_loans = await service.open_loans_by_equipment_id()
            rows = [
                {
                    'id': a.id,
                    'asset_number': a.asset_number,
                    'name': a.name,
                    'owner': a.owner_label,
                    'status': _STATUS_LABELS.get(a.status.value, a.status.value),
                    'status_value': a.status.value,
                    'holder': (
                        open_loans[a.id].borrower.preferred_name
                        if a.id in open_loans else '-'
                    ),
                }
                for a in assets
            ]

            table = ui.table(columns=_COLUMNS, rows=rows, row_key='id').classes(
                'equipment-table equipment-table-container w-full'
            ).props(':grid="Quasar.Screen.lt.md"')
            table.add_slot('body-cell-status', '''<q-td :props="props">
                <q-badge :color="props.row.status_value === 'available' ? 'positive'
                                 : props.row.status_value === 'checked_out' ? 'warning' : 'grey'">
                    {{ props.value }}
                </q-badge>
            </q-td>''')
            table.add_slot('body-cell-actions', '''<q-td :props="props">
                <q-btn v-if="props.row.status_value === 'available'" dense flat round icon="logout" color="primary"
                       @click="$parent.$emit('checkout', props.row)"><q-tooltip>Check out</q-tooltip></q-btn>
                <q-btn v-if="props.row.status_value === 'checked_out'" dense flat round icon="login" color="secondary"
                       @click="$parent.$emit('checkin', props.row)"><q-tooltip>Check in</q-tooltip></q-btn>
                <q-btn dense flat round icon="qr_code_2" color="primary"
                       @click="$parent.$emit('view', props.row)"><q-tooltip>Open asset page</q-tooltip></q-btn>
                <q-btn dense flat round icon="edit" color="primary"
                       @click="$parent.$emit('edit', props.row)"><q-tooltip>Edit</q-tooltip></q-btn>
                <q-btn dense flat round icon="delete" color="negative"
                       @click="$parent.$emit('remove', props.row)"><q-tooltip>Delete</q-tooltip></q-btn>
            </q-td>''')
            table.add_slot('item', '''<div class="q-pa-sm q-mb-sm equipment-grid-card" style="width: 100%; box-sizing: border-box;">
                <div class="row items-center q-mb-xs">
                    <div class="col-4 text-grey-7">#:</div>
                    <div class="col-8">{{ props.row.asset_number }}</div>
                </div>
                <div class="row items-center q-mb-xs">
                    <div class="col-4 text-grey-7">Name:</div>
                    <div class="col-8">{{ props.row.name }}</div>
                </div>
                <div class="row items-center q-mb-xs">
                    <div class="col-4 text-grey-7">Owner:</div>
                    <div class="col-8">{{ props.row.owner }}</div>
                </div>
                <div class="row items-center q-mb-xs">
                    <div class="col-4 text-grey-7">Status:</div>
                    <div class="col-8">
                        <q-badge :color="props.row.status_value === 'available' ? 'positive'
                                         : props.row.status_value === 'checked_out' ? 'warning' : 'grey'">
                            {{ props.row.status }}
                        </q-badge>
                    </div>
                </div>
                <div class="row items-center q-mb-xs">
                    <div class="col-4 text-grey-7">Checked out to:</div>
                    <div class="col-8">{{ props.row.holder }}</div>
                </div>
                <div class="row items-center justify-end q-gutter-xs">
                    <q-btn v-if="props.row.status_value === 'available'" dense flat round icon="logout" color="primary"
                           @click="$parent.$emit('checkout', props.row)"><q-tooltip>Check out</q-tooltip></q-btn>
                    <q-btn v-if="props.row.status_value === 'checked_out'" dense flat round icon="login" color="secondary"
                           @click="$parent.$emit('checkin', props.row)"><q-tooltip>Check in</q-tooltip></q-btn>
                    <q-btn dense flat round icon="qr_code_2" color="primary"
                           @click="$parent.$emit('view', props.row)"><q-tooltip>Open asset page</q-tooltip></q-btn>
                    <q-btn dense flat round icon="edit" color="primary"
                           @click="$parent.$emit('edit', props.row)"><q-tooltip>Edit</q-tooltip></q-btn>
                    <q-btn dense flat round icon="delete" color="negative"
                           @click="$parent.$emit('remove', props.row)"><q-tooltip>Delete</q-tooltip></q-btn>
                </div>
            </div>''')

            def handle_view(event):
                ui.navigate.to(f"/equipment/{event.args['id']}")

            async def handle_checkout(row, client):
                with client:
                    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                    await open_checkout(actor, row['id'], can_manage=True, on_done=_render_table.refresh)

            async def handle_checkin(row, client):
                with client:
                    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                    await quick_checkin(actor, row['id'], on_done=_render_table.refresh)

            async def handle_edit(row, client):
                with client:
                    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                    asset = await service.get_asset(row['id'])
                    if asset is None:
                        ui.notify('Asset not found.', color='warning')
                        return
                    await EquipmentDialog(actor, equipment=asset, on_saved=_render_table.refresh).open()

            async def handle_remove(row, client):
                with client:
                    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))

                    async def do_delete():
                        confirm.dialog.close()
                        try:
                            await service.delete_asset(actor, row['id'])
                        except (ValueError, PermissionError) as e:
                            notify_error(e)
                            return
                        ui.notify('Asset deleted.', color='positive')
                        await _render_table.refresh()

                    confirm = ConfirmationDialog(
                        message=f"Delete asset #{row['asset_number']} ({row['name']})?",
                        on_confirm=do_delete,
                        confirm_text='Delete',
                    )
                    confirm.open()

            table.on('view', handle_view)
            table.on('checkout', lambda e: background_tasks.create(handle_checkout(e.args, context.client)))
            table.on('checkin', lambda e: background_tasks.create(handle_checkin(e.args, context.client)))
            table.on('edit', lambda e: background_tasks.create(handle_edit(e.args, context.client)))
            table.on('remove', lambda e: background_tasks.create(handle_remove(e.args, context.client)))

        await _render_table()
