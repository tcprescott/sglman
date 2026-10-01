"""Admin → Users → ADA requests: the staff queue for accommodation requests.

Rendered as a sub-tab of Users rather than a drawer entry of its own, because a
request is a fact about a member and staff reach it from the member list. STAFF
only (the Users tab already is, and the service checks again).

Each row opens one dialog that sets the status and the staff-only notes in a
single save. The requester's details are read-only here; only they can change
them, from their profile.
"""

from typing import Any, Awaitable, Callable, Optional

from nicegui import ui

from application.services import AccommodationService, TenantService
from application.services.accommodation_service import STAFF_NOTES_MAX_LENGTH
from application.utils.timezone import format_local_display
from models import AccommodationStatus
from theme.accommodation_copy import STATUS_CHIP, STATUS_LABELS, privacy_disclaimer
from theme.dialog._helpers import dialog_actions, form_dialog
from theme.empty_state import no_data_slot
from theme.notify import notify_error
from theme.tables.admin_crud import current_actor, refresh_button
from theme.tables.export import csv_export_button
from theme.tables.mobile_grid import enable_mobile_grid
from theme.tables.preferences import TableKeys

_WRAP = 'white-space: pre-wrap; min-width: 200px; max-width: 360px'

_COLUMNS: list[dict[str, Any]] = [
    {'name': 'created_at', 'label': 'Requested', 'field': 'created_at', 'align': 'left', 'sortable': True},
    {'name': 'user', 'label': 'Member', 'field': 'user', 'align': 'left', 'sortable': True},
    {'name': 'status', 'label': 'Status', 'field': 'status_label', 'align': 'left', 'sortable': True},
    {'name': 'details', 'label': 'Details', 'field': 'details', 'align': 'left', 'style': _WRAP},
    {'name': 'staff_notes', 'label': 'Staff notes', 'field': 'staff_notes', 'align': 'left', 'style': _WRAP},
    {'name': 'updated_at', 'label': 'Updated', 'field': 'updated_at', 'align': 'left', 'sortable': True},
    {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
]

_STATUS_BADGE = '''
    <span :class="'wiz-chip ' + props.row.status_chip" style="white-space: nowrap">{{ props.row.status_label }}</span>
'''

_ROW_ACTIONS = '''
    <q-btn dense flat no-wrap color="primary" icon="edit_note" label="Update"
           @click="$parent.$emit('edit_request', props.row)" />
'''

_EDITABLE_STATUSES = {
    s.value: STATUS_LABELS[s]
    for s in (AccommodationStatus.NEW, AccommodationStatus.ACKNOWLEDGED, AccommodationStatus.ARRANGED)
}


async def render_accommodation_panel(
    on_change: Optional[Callable[[], Awaitable[None]]] = None,
) -> None:
    """The request queue. ``on_change`` runs after a save (e.g. to recount the tab label)."""
    service = AccommodationService()
    community = await TenantService.current_community_name()
    state: dict[str, Any] = {'include_withdrawn': False, 'rows': []}

    ui.label(
        'Members who asked for ADA accommodation, oldest first. Update a '
        'request to set its status and add notes only staff can see.'
    ).classes('text-caption text-grey')
    with ui.row().classes('items-center full-width'):
        ui.space()
        ui.checkbox(
            'Show withdrawn',
            on_change=lambda e: (state.update(include_withdrawn=e.value), _render_table.refresh()),
        ).props('dense')
        csv_export_button(
            'ada-requests',
            lambda: [c for c in _COLUMNS if c['name'] != 'actions'],
            lambda: state['rows'],
        )
        refresh_button(lambda: _render_table.refresh(), tooltip='Refresh')

    with ui.row().classes('items-start gap-2 no-wrap'):
        ui.icon('privacy_tip', size='sm').classes('text-warning')
        ui.label(privacy_disclaimer(community)).classes('text-caption text-warning col')

    async def open_editor(row: dict) -> None:
        withdrawn = row['status'] == AccommodationStatus.WITHDRAWN.value
        with form_dialog(f"ADA request: {row['user']}") as dialog:
            with ui.column().classes('q-pa-md gap-2 full-width'):
                ui.label(f"Requested {row['created_at']}").classes('text-caption text-muted')
                ui.label('Details from the member').classes('subsection-title')
                ui.label(row['details'] or 'No details given.') \
                    .classes('text-body2').style('white-space: pre-wrap')
                if withdrawn:
                    ui.label(
                        'Withdrawn by the member. It reopens as New if they ask again.'
                    ).classes('text-caption text-grey')
                    status_select = None
                else:
                    status_select = ui.select(
                        _EDITABLE_STATUSES, value=row['status'], label='Status',
                    ).props('outlined dense stack-label').classes('w-full')
                notes = ui.textarea(
                    'Staff notes', value=row['staff_notes'],
                    placeholder='e.g. seat near the stage door arranged with venue',
                ).props(f'outlined autogrow stack-label counter maxlength={STAFF_NOTES_MAX_LENGTH}') \
                    .classes('w-full')
                ui.label('The member never sees staff notes.').classes('text-caption text-grey')

            async def submit() -> None:
                actor = await current_actor()
                status = status_select.value if status_select else row['status']
                try:
                    await service.update_request(actor, row['id'], status, notes.value)
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                dialog.close()
                ui.notify('Request updated.', color='positive')
                await _render_table.refresh()
                if on_change:
                    await on_change()

            with dialog_actions().classes('justify-end'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save', on_click=submit).props('color=primary')
        dialog.open()

    @ui.refreshable
    async def _render_table() -> None:
        actor = await current_actor()
        try:
            requests = await service.list_requests(actor, include_withdrawn=state['include_withdrawn'])
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        state['rows'] = [
            {
                'id': r.id,
                'created_at': format_local_display(r.created_at),
                'updated_at': format_local_display(r.updated_at),
                'user': r.user.preferred_name,
                'status': r.status.value,
                'status_label': STATUS_LABELS[r.status],
                'status_chip': STATUS_CHIP[r.status],
                'details': r.details or '',
                'staff_notes': r.staff_notes or '',
            }
            for r in requests
        ]
        table = ui.table(columns=_COLUMNS, rows=state['rows'], row_key='id').classes('w-full wiz-table')
        table.add_slot('body-cell-status', f'<q-td :props="props">{_STATUS_BADGE}</q-td>')
        table.add_slot('body-cell-actions', f'<q-td :props="props">{_ROW_ACTIONS}</q-td>')
        table.add_slot('no-data', no_data_slot(
            'Nobody has asked for an ADA accommodation yet.', icon='accessible',
        ))
        enable_mobile_grid(table, _COLUMNS, actions=_ROW_ACTIONS,
                           table_key=TableKeys.ADMIN_ACCOMMODATIONS,
                           field_slots={'status': _STATUS_BADGE}, wrap=True)
        table.on('edit_request', lambda e: open_editor(e.args))

    await _render_table()
