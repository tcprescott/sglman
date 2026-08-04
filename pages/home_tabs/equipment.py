"""What the viewer currently has checked out, as a My Schedule section.

This module used to be Home's Equipment *tab*, carrying a full inventory browser
alongside the viewer's own loans. The inventory left the player surface when Home
came down to four tabs: browsing the cage is staff work and lives on Admin →
Equipment, while the way an attendee actually borrows something is scanning the
QR code on the device itself, which lands on ``/equipment/<id>`` and checks out
from there. What remained worth showing a player is the answer to "what am I
still holding?", which is this.
"""

from nicegui import app, ui

from application.services import EquipmentService, get_user_from_discord_id
from application.utils.timezone import format_local_display
from theme.connection import REQUIRES_SOCKET_CLASS
from theme.section import section_panel
from theme.tables.preferences import TableKeys, customize_table, preferences_button

_MINE_COLUMNS: list[dict] = [
    {'name': 'asset_number', 'label': '#', 'field': 'asset_number', 'align': 'left', 'sortable': True},
    {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left', 'sortable': True},
    {'name': 'checked_out_at', 'label': 'Checked out', 'field': 'checked_out_at', 'align': 'left'},
    {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
]

# Desktop keeps the icon — a tooltip opens on a mouse, and the row has no space
# for a label. The mobile card carries text, because this section is read on a
# phone where a tooltip never opens. Both forms come from one spec so they cannot
# drift, and each carries the offline guard's class (theme/connection.py):
# View's navigation is a server round trip, not an <a href>.
_VIEW = {'event': 'view', 'icon': 'open_in_new', 'color': 'primary', 'label': 'View',
         'tooltip': 'View asset'}

_VIEW_ICON_BTN = (
    f'<q-btn dense flat round icon="{_VIEW["icon"]}" color="{_VIEW["color"]}"\n'
    f'               class="{REQUIRES_SOCKET_CLASS}"\n'
    f'               @click="$parent.$emit(\'{_VIEW["event"]}\', props.row)">'
    f'<q-tooltip>{_VIEW["tooltip"]}</q-tooltip></q-btn>'
)

_VIEW_LABEL_BTN = (
    f'<q-btn dense no-caps flat icon="{_VIEW["icon"]}" color="{_VIEW["color"]}"\n'
    f'               label="{_VIEW["label"]}" class="{REQUIRES_SOCKET_CLASS}"\n'
    f'               @click="$parent.$emit(\'{_VIEW["event"]}\', props.row)" />'
)


async def equipment_checkouts_section() -> None:
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    if user is None:
        return

    service = EquipmentService()

    panel = await section_panel(
        'Equipment you have out',
        icon='inventory_2',
        subtitle='Gear checked out to you and not yet returned.',
        user=user,
    )
    with panel.body:
        loans = await service.my_checkouts(user)
        if not loans:
            ui.label('You have no equipment checked out.').classes('italic-note')
            return

        rows = [
            {
                'id': loan.equipment_id,
                'asset_number': loan.equipment.asset_number,
                'name': loan.equipment.name,
                'checked_out_at': format_local_display(loan.checked_out_at),
            }
            for loan in loans
        ]
        table = ui.table(columns=_MINE_COLUMNS, rows=rows, row_key='id').classes(
            'equipment-table equipment-table-container w-full'
        ).props(':grid="Quasar.Screen.lt.md"')
        table.add_slot('body-cell-actions',
                       '<q-td :props="props">' + _VIEW_ICON_BTN + '</q-td>')
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
            <div class="row items-center justify-end">''' + _VIEW_LABEL_BTN + '''</div>
        </div>''')
        customize_table(table, _MINE_COLUMNS, key=TableKeys.EQUIPMENT_MINE)
        # In the panel header: on its own row above the table it was a lone icon
        # floating in an otherwise empty band.
        with panel.aside:
            preferences_button(table)
        table.on('view', lambda e: ui.navigate.to(f"/equipment/{e.args['id']}"))
