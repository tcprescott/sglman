"""Home Equipment tab — inventory browsing and the user's own checkouts."""

from nicegui import app, background_tasks, context, ui

from application.services import AuthService, EquipmentService, get_user_from_discord_id
from application.utils.timezone import format_eastern_display
from theme.dialog import open_checkout, quick_checkin

_STATUS_LABELS = {
    'available': 'Available',
    'checked_out': 'Checked out',
    'retired': 'Retired',
}

_INVENTORY_COLUMNS = [
    {'name': 'asset_number', 'label': '#', 'field': 'asset_number', 'align': 'left', 'sortable': True},
    {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
    {'name': 'status', 'label': 'Status', 'field': 'status', 'align': 'left', 'sortable': True},
    {'name': 'holder', 'label': 'Checked out to', 'field': 'holder', 'align': 'left'},
    {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
]

_MINE_COLUMNS = [
    {'name': 'asset_number', 'label': '#', 'field': 'asset_number', 'align': 'left', 'sortable': True},
    {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
    {'name': 'checked_out_at', 'label': 'Checked out', 'field': 'checked_out_at', 'align': 'left'},
    {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
]


async def equipment_tab() -> None:
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    if user is None:
        ui.label('You must be logged in.').classes('text-error')
        return

    service = EquipmentService()
    can_manage = await AuthService.can_manage_equipment(user)
    can_checkout = await AuthService.can_checkout_equipment(user)
    can_checkin = await AuthService.can_checkin_equipment(user)

    with ui.column().classes('page-container w-full'):
        with ui.row().classes('header-row'):
            ui.label('Equipment').classes('page-title')
        ui.separator().classes('separator-spacing')

        with ui.tabs().classes('w-full') as inner_tabs:
            ui.tab('inventory', label='Inventory', icon='inventory_2')
            ui.tab('mine', label='My Checkouts', icon='assignment_ind')

        with ui.tab_panels(inner_tabs, value='inventory').classes('w-full'):
            with ui.tab_panel('inventory'):
                @ui.refreshable
                async def inventory_table() -> None:
                    assets = await service.list_assets()
                    open_loans = await service.open_loans_by_equipment_id()
                    rows = [
                        {
                            'id': a.id,
                            'asset_number': a.asset_number,
                            'name': a.name,
                            'status': _STATUS_LABELS.get(a.status.value, a.status.value),
                            'status_value': a.status.value,
                            'holder': (
                                open_loans[a.id].borrower.preferred_name
                                if a.id in open_loans else '-'
                            ),
                        }
                        for a in assets
                    ]
                    table = ui.table(
                        columns=_INVENTORY_COLUMNS, rows=rows, row_key='id'
                    ).classes('equipment-table equipment-table-container w-full').props(
                        ':grid="Quasar.Screen.lt.md"'
                    )
                    checkout_btn = '''<q-btn v-if="props.row.status_value === 'available'" dense flat round icon="logout" color="primary"
                               @click="$parent.$emit('checkout', props.row)"><q-tooltip>Check out</q-tooltip></q-btn>''' if can_checkout else ''
                    checkin_btn = '''<q-btn v-if="props.row.status_value === 'checked_out'" dense flat round icon="login" color="secondary"
                               @click="$parent.$emit('checkin', props.row)"><q-tooltip>Check in</q-tooltip></q-btn>''' if can_checkin else ''
                    view_btn = '''<q-btn dense flat round icon="open_in_new" color="primary"
                               @click="$parent.$emit('view', props.row)"><q-tooltip>View asset</q-tooltip></q-btn>'''

                    table.add_slot('body-cell-status', '''<q-td :props="props">
                        <q-badge :color="props.row.status_value === 'available' ? 'positive'
                                         : props.row.status_value === 'checked_out' ? 'warning' : 'grey'">
                            {{ props.value }}
                        </q-badge>
                    </q-td>''')
                    table.add_slot('body-cell-actions',
                        '<q-td :props="props">' + checkout_btn + checkin_btn + view_btn + '</q-td>')
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
                        <div class="row items-center justify-end">''' + checkout_btn + checkin_btn + view_btn + '''</div>
                    </div>''')

                    async def handle_checkout(row, client):
                        with client:
                            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                            await open_checkout(actor, row['id'], can_manage=can_manage, on_done=inventory_table.refresh)

                    async def handle_checkin(row, client):
                        with client:
                            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                            await quick_checkin(actor, row['id'], on_done=inventory_table.refresh)

                    table.on('view', lambda e: ui.navigate.to(f"/equipment/{e.args['id']}"))
                    table.on('checkout', lambda e: background_tasks.create(handle_checkout(e.args, context.client)))
                    table.on('checkin', lambda e: background_tasks.create(handle_checkin(e.args, context.client)))

                await inventory_table()

            with ui.tab_panel('mine'):
                @ui.refreshable
                async def my_table() -> None:
                    loans = await service.my_checkouts(user)
                    rows = [
                        {
                            'id': loan.equipment_id,
                            'asset_number': loan.equipment.asset_number,
                            'name': loan.equipment.name,
                            'checked_out_at': format_eastern_display(loan.checked_out_at),
                        }
                        for loan in loans
                    ]
                    if not rows:
                        ui.label('You have no equipment checked out.').classes('italic-note')
                        return
                    table = ui.table(columns=_MINE_COLUMNS, rows=rows, row_key='id').classes(
                        'equipment-table equipment-table-container w-full'
                    ).props(':grid="Quasar.Screen.lt.md"')
                    table.add_slot('body-cell-actions', '''<q-td :props="props">
                        <q-btn dense flat round icon="open_in_new" color="primary"
                               @click="$parent.$emit('view', props.row)"><q-tooltip>View asset</q-tooltip></q-btn>
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
                            <div class="col-4 text-grey-7">Checked out:</div>
                            <div class="col-8">{{ props.row.checked_out_at }}</div>
                        </div>
                        <div class="row items-center justify-end">
                            <q-btn dense flat round icon="open_in_new" color="primary"
                                   @click="$parent.$emit('view', props.row)"><q-tooltip>View asset</q-tooltip></q-btn>
                        </div>
                    </div>''')
                    table.on('view', lambda e: ui.navigate.to(f"/equipment/{e.args['id']}"))

                await my_table()
