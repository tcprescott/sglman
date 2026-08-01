"""Admin Equipment Management Page (Equipment Manager / Staff)."""

from nicegui import app, background_tasks, context, ui

from application.services import EquipmentService, TenantService, get_user_from_discord_id
from theme.connection import REQUIRES_SOCKET_CLASS
from theme.dialog import ConfirmationDialog, EquipmentDialog, QrLabelDialog, open_checkout, quick_checkin
from theme.notify import notify_error
from theme.tables.admin_crud import refresh_button
from theme.tables.preferences import (
    TableKeys,
    customize_table,
    preferences_button,
    search_input,
)

_STATUS_LABELS = {
    'available': 'Available',
    'checked_out': 'Checked out',
    'retired': 'Retired',
}

_COLUMNS: list[dict] = [
    {'name': 'asset_number', 'label': '#', 'field': 'asset_number', 'align': 'left', 'sortable': True},
    {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
    {'name': 'owner', 'label': 'Owner', 'field': 'owner', 'align': 'left'},
    {'name': 'status', 'label': 'Status', 'field': 'status', 'align': 'left', 'sortable': True},
    {'name': 'holder', 'label': 'Checked out to', 'field': 'holder', 'align': 'left'},
    {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
]

_STATUS_CELL = '''<q-td :props="props">
    <q-badge :color="props.row.status_value === 'available' ? 'positive'
                     : props.row.status_value === 'checked_out' ? 'warning' : 'grey'">
        {{ props.value }}
    </q-badge>
</q-td>'''

_STATUS_BADGE = '''<q-badge :color="props.row.status_value === 'available' ? 'positive'
                                 : props.row.status_value === 'checked_out' ? 'warning' : 'grey'">
                    {{ props.row.status }}
                </q-badge>'''

# Desktop stays icon-only: a tooltip does open on a mouse, and the wide row has
# no space for four labels. Every button emits, so every button needs the socket
# and carries the offline guard's class (theme/connection.py) — the test asserts
# that count matches, in this slot and in the card below.
_ACTIONS_CELL = f'''<q-td :props="props">
    <q-btn v-if="props.row.status_value === 'available'" dense flat round icon="logout" color="primary"
           class="{REQUIRES_SOCKET_CLASS}"
           @click="$parent.$emit('checkout', props.row)"><q-tooltip>Check out</q-tooltip></q-btn>
    <q-btn v-if="props.row.status_value === 'checked_out'" dense flat round icon="login" color="secondary"
           class="{REQUIRES_SOCKET_CLASS}"
           @click="$parent.$emit('checkin', props.row)"><q-tooltip>Check in</q-tooltip></q-btn>
    <q-btn dense flat round icon="qr_code_2" color="primary" class="{REQUIRES_SOCKET_CLASS}"
           @click="$parent.$emit('view', props.row)"><q-tooltip>Open asset page</q-tooltip></q-btn>
    <q-btn dense flat round icon="edit" color="primary" class="{REQUIRES_SOCKET_CLASS}"
           @click="$parent.$emit('edit', props.row)"><q-tooltip>Edit</q-tooltip></q-btn>
    <q-btn dense flat round icon="delete" color="negative" class="{REQUIRES_SOCKET_CLASS}"
           @click="$parent.$emit('remove', props.row)"><q-tooltip>Delete</q-tooltip></q-btn>
</q-td>'''

_GRID_CARD = f'''<div class="q-pa-sm q-mb-sm equipment-grid-card" style="width: 100%; box-sizing: border-box;">
    <div class="row items-center q-mb-xs">
        <div class="col-4 text-grey-7">#:</div>
        <div class="col-8">{{{{ props.row.asset_number }}}}</div>
    </div>
    <div class="row items-center q-mb-xs">
        <div class="col-4 text-grey-7">Name:</div>
        <div class="col-8">{{{{ props.row.name }}}}</div>
    </div>
    <div class="row items-center q-mb-xs">
        <div class="col-4 text-grey-7">Owner:</div>
        <div class="col-8">{{{{ props.row.owner }}}}</div>
    </div>
    <div class="row items-center q-mb-xs">
        <div class="col-4 text-grey-7">Status:</div>
        <div class="col-8">
            {_STATUS_BADGE}
        </div>
    </div>
    <div class="row items-center q-mb-xs">
        <div class="col-4 text-grey-7">Checked out to:</div>
        <div class="col-8">{{{{ props.row.holder }}}}</div>
    </div>
    <!-- Labelled, not icon-only: this register is read on a phone at the venue,
         where a tooltip never opens — the same reason the proctor card's buttons
         carry text (theme/tables/match_slots.py). Delete is on its own line, so
         the destructive control is not a thumb-width from Edit. -->
    <div class="row items-center justify-end q-gutter-xs">
        <q-btn v-if="props.row.status_value === 'available'" dense no-caps icon="logout" color="primary"
               label="Check out" class="{REQUIRES_SOCKET_CLASS}"
               @click="$parent.$emit('checkout', props.row)" />
        <q-btn v-if="props.row.status_value === 'checked_out'" dense no-caps icon="login" color="secondary"
               label="Check in" class="{REQUIRES_SOCKET_CLASS}"
               @click="$parent.$emit('checkin', props.row)" />
        <q-btn dense no-caps flat icon="qr_code_2" color="primary" label="Open"
               class="{REQUIRES_SOCKET_CLASS}"
               @click="$parent.$emit('view', props.row)" />
        <q-btn dense no-caps flat icon="edit" color="primary" label="Edit"
               class="{REQUIRES_SOCKET_CLASS}"
               @click="$parent.$emit('edit', props.row)" />
    </div>
    <div class="row items-center justify-end q-mt-sm">
        <q-btn dense no-caps outline icon="delete" color="negative" label="Delete"
               class="{REQUIRES_SOCKET_CLASS}"
               @click="$parent.$emit('remove', props.row)" />
    </div>
</div>'''


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

            async def print_labels():
                actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                await QrLabelDialog(actor).open()

            ui.button('Add Asset', icon='add', on_click=add_asset).props(
                'color=primary').classes(REQUIRES_SOCKET_CLASS)
            ui.button('Print QR labels', icon='qr_code_2', on_click=print_labels).props(
                'flat color=primary').classes(REQUIRES_SOCKET_CLASS)
            ui.space()
            # Filled from inside _render_table, which owns the table.
            gear_slot = ui.row().classes('items-center')
            # Lambda, not a direct reference: the toolbar is built before
            # _render_table exists.
            refresh_button(lambda: _render_table.refresh(), tooltip='Refresh') \
                .classes(REQUIRES_SOCKET_CLASS)

        @ui.refreshable
        async def _render_table() -> None:
            assets = await service.list_assets()
            open_loans = await service.open_loans_by_equipment_id()
            community = await TenantService.current_community_name()
            rows = [
                {
                    'id': a.id,
                    'asset_number': a.asset_number,
                    'name': a.name,
                    'owner': a.owner_label(community),
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
            table.add_slot('body-cell-status', _STATUS_CELL)
            table.add_slot('body-cell-actions', _ACTIONS_CELL)
            table.add_slot('item', _GRID_CARD)
            # After the card slot, never before — the card is built from the
            # shipped columns and must not follow a saved layout.
            customize_table(table, _COLUMNS, key=TableKeys.ADMIN_EQUIPMENT)
            # Cleared first: this whole block re-runs on every refresh, and the
            # gear lives outside it so it would otherwise stack up.
            gear_slot.clear()
            with gear_slot:
                search_input(table, placeholder='Search equipment…')
                preferences_button(table)

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
                        ui.notify("Couldn't find that asset. Try refreshing.", color='warning')
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
