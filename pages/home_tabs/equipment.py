"""Home Equipment tab — inventory browsing and the user's own checkouts."""

from nicegui import app, background_tasks, context, ui

from application.services import AuthService, EquipmentService, get_user_from_discord_id
from application.utils.timezone import format_local_display
from theme.connection import REQUIRES_SOCKET_CLASS
from theme.dialog import open_checkout, quick_checkin
from theme.tables.preferences import TableKeys, customize_table, preferences_button

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

# Desktop keeps icons — a tooltip opens on a mouse, and the wide row has no space
# for labels. The mobile card carries text, because this tab is read on a phone
# where a tooltip never opens; same reason the proctor card's buttons are
# labelled (theme/tables/match_slots.py). Both forms come from one spec, so the
# two copies cannot drift on which actions exist, and every one of them carries
# the offline guard's class (theme/connection.py) — including View, whose
# navigation is a server round trip, not an <a href>.
_ACTIONS = (
    {'event': 'checkout', 'icon': 'logout', 'color': 'primary', 'label': 'Check out',
     'tooltip': 'Check out', 'when': "props.row.status_value === 'available'"},
    {'event': 'checkin', 'icon': 'login', 'color': 'secondary', 'label': 'Check in',
     'tooltip': 'Check in', 'when': "props.row.status_value === 'checked_out'"},
    {'event': 'view', 'icon': 'open_in_new', 'color': 'primary', 'label': 'View',
     'tooltip': 'View asset', 'when': None},
)


def _icon_btn(spec: dict) -> str:
    guard = f'v-if="{spec["when"]}" ' if spec['when'] else ''
    return (
        f'<q-btn {guard}dense flat round icon="{spec["icon"]}" color="{spec["color"]}"\n'
        f'               class="{REQUIRES_SOCKET_CLASS}"\n'
        f'               @click="$parent.$emit(\'{spec["event"]}\', props.row)">'
        f'<q-tooltip>{spec["tooltip"]}</q-tooltip></q-btn>'
    )


def _label_btn(spec: dict) -> str:
    guard = f'v-if="{spec["when"]}" ' if spec['when'] else ''
    return (
        f'<q-btn {guard}dense no-caps flat icon="{spec["icon"]}" color="{spec["color"]}"\n'
        f'               label="{spec["label"]}" class="{REQUIRES_SOCKET_CLASS}"\n'
        f'               @click="$parent.$emit(\'{spec["event"]}\', props.row)" />'
    )


_ICON_BTNS = {spec['event']: _icon_btn(spec) for spec in _ACTIONS}
_LABEL_BTNS = {spec['event']: _label_btn(spec) for spec in _ACTIONS}
# "My Checkouts" offers only View; its own card is labelled the same way.
_MINE_ICON_BTN = _ICON_BTNS['view']
_MINE_LABEL_BTN = _LABEL_BTNS['view']


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
                    gear_slot = ui.row().classes('full-width justify-end')
                    table = ui.table(
                        columns=_INVENTORY_COLUMNS, rows=rows, row_key='id'
                    ).classes('equipment-table equipment-table-container w-full').props(
                        ':grid="Quasar.Screen.lt.md"'
                    )
                    def actions(btns: dict) -> str:
                        return (
                            (btns['checkout'] if can_checkout else '')
                            + (btns['checkin'] if can_checkin else '')
                            + btns['view']
                        )

                    table.add_slot('body-cell-status', '''<q-td :props="props">
                        <q-badge :color="props.row.status_value === 'available' ? 'positive'
                                         : props.row.status_value === 'checked_out' ? 'warning' : 'grey'">
                            {{ props.value }}
                        </q-badge>
                    </q-td>''')
                    table.add_slot('body-cell-actions',
                        '<q-td :props="props">' + actions(_ICON_BTNS) + '</q-td>')
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
                        <div class="row items-center justify-end q-gutter-xs">''' + actions(_LABEL_BTNS) + '''</div>
                    </div>''')
                    customize_table(table, _INVENTORY_COLUMNS,
                                    key=TableKeys.EQUIPMENT_INVENTORY)
                    with gear_slot:
                        preferences_button(table)

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
                            'checked_out_at': format_local_display(loan.checked_out_at),
                        }
                        for loan in loans
                    ]
                    if not rows:
                        ui.label('You have no equipment checked out.').classes('italic-note')
                        return
                    gear_slot = ui.row().classes('full-width justify-end')
                    table = ui.table(columns=_MINE_COLUMNS, rows=rows, row_key='id').classes(
                        'equipment-table equipment-table-container w-full'
                    ).props(':grid="Quasar.Screen.lt.md"')
                    table.add_slot('body-cell-actions',
                        '<q-td :props="props">' + _MINE_ICON_BTN + '</q-td>')
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
                        <div class="row items-center justify-end">''' + _MINE_LABEL_BTN + '''</div>
                    </div>''')
                    customize_table(table, _MINE_COLUMNS, key=TableKeys.EQUIPMENT_MINE)
                    with gear_slot:
                        preferences_button(table)
                    table.on('view', lambda e: ui.navigate.to(f"/equipment/{e.args['id']}"))

                await my_table()
