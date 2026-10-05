"""Admin → Check-in: set up the events the check-in desk runs (Staff).

Each event names a Matcherino bounty whose registrations become the desk's
roster. Opening an event puts it on the desk and starts the background sync;
the desk itself lives at ``/checkin``.
"""

from nicegui import background_tasks, context, ui

from application.services import CheckInService
from application.utils.timezone import format_local_display
from models import CheckInEventStatus
from theme.connection import REQUIRES_SOCKET_CLASS
from theme.dialog import ConfirmationDialog
from theme.dialog.check_in_dialogs import open_event_dialog
from theme.notify import notify_error
from theme.tables.admin_crud import current_actor, refresh_button
from theme.tables.mobile_grid import enable_mobile_grid
from theme.tables.preferences import TableKeys

_STATUS_LABELS = {
    CheckInEventStatus.DRAFT.value: 'Draft',
    CheckInEventStatus.OPEN.value: 'Open',
    CheckInEventStatus.CLOSED.value: 'Closed',
}

_COLUMNS: list[dict] = [
    {'name': 'id', 'label': 'ID', 'field': 'id', 'hidden': True},
    {'name': 'name', 'label': 'Event', 'field': 'name', 'align': 'left', 'sortable': True},
    {'name': 'status', 'label': 'Status', 'field': 'status_label', 'align': 'left', 'sortable': True},
    {'name': 'bounty', 'label': 'Matcherino bounty', 'field': 'bounty', 'align': 'left'},
    {'name': 'synced', 'label': 'Last sync', 'field': 'synced', 'align': 'left'},
    {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
]

_STATUS_BADGE = '''<q-badge :color="props.row.status === 'open' ? 'positive'
                                 : props.row.status === 'draft' ? 'grey-7' : 'blue-grey'">
    {{ props.row.status_label }}</q-badge>'''

_SYNCED = '''<span :class="props.row.sync_error ? 'text-warning' : ''">{{ props.row.synced }}</span>'''

_ACTIONS = f'''
    <q-btn dense flat no-caps icon="how_to_reg" color="primary" label="Desk"
           class="{REQUIRES_SOCKET_CLASS}" @click="$parent.$emit('desk', props.row)" />
    <q-btn dense flat round icon="edit" color="primary" class="{REQUIRES_SOCKET_CLASS}"
           @click="$parent.$emit('edit', props.row)"><q-tooltip>Edit</q-tooltip></q-btn>
    <q-btn dense flat round icon="delete" color="negative" class="{REQUIRES_SOCKET_CLASS}"
           @click="$parent.$emit('remove', props.row)"><q-tooltip>Delete</q-tooltip></q-btn>
'''


def _synced_text(event) -> str:
    if event.matcherino_bounty_id is None:
        return 'Walk-ups only'
    if event.last_sync_error:
        return f'Failed: {event.last_sync_error}'
    if event.last_synced_at is None:
        return 'Not yet'
    return f'{format_local_display(event.last_synced_at)} · {event.last_sync_count or 0} registered'


async def admin_check_in_page() -> None:
    service = CheckInService()

    with ui.column().classes('page-container-narrow w-full'):
        with ui.row().classes('header-row'):
            ui.label('Check-in').classes('page-title')
        ui.label(
            'Each event pulls its roster from a Matcherino bounty. Open an event to '
            'put it on the check-in desk; the desk syncs on its own while it is open.'
        ).classes('text-caption text-grey-7')
        ui.separator().classes('separator-spacing')

        with ui.row().classes('full-width items-center'):
            async def add_event() -> None:
                actor = await current_actor()
                if actor is None:
                    return
                await open_event_dialog(service, actor, on_done=_render_table.refresh)

            ui.button('New event', icon='add', on_click=add_event).props('color=primary') \
                .classes(REQUIRES_SOCKET_CLASS)
            ui.space()
            refresh_button(lambda: _render_table.refresh(), tooltip='Refresh').classes(REQUIRES_SOCKET_CLASS)

        @ui.refreshable
        async def _render_table() -> None:
            events = await service.list_events()
            rows = [
                {
                    'id': e.id,
                    'name': e.name,
                    'status': e.status.value,
                    'status_label': _STATUS_LABELS.get(e.status.value, e.status.value),
                    'bounty': str(e.matcherino_bounty_id) if e.matcherino_bounty_id else '—',
                    'synced': _synced_text(e),
                    'sync_error': bool(e.last_sync_error),
                }
                for e in events
            ]
            table = ui.table(columns=_COLUMNS, rows=rows, row_key='id').classes('w-full')
            table.add_slot('body-cell-status', f'<q-td :props="props">{_STATUS_BADGE}</q-td>')
            table.add_slot('body-cell-synced', f'<q-td :props="props">{_SYNCED}</q-td>')
            table.add_slot('body-cell-actions', f'<q-td :props="props">{_ACTIONS}</q-td>')
            table.add_slot('no-data', '''<div class="full-width text-center text-grey-7 q-pa-md">
                No check-in events yet. Create one for your next in-person event.</div>''')
            enable_mobile_grid(
                table, _COLUMNS, actions=_ACTIONS,
                field_slots={'status': _STATUS_BADGE, 'synced': _SYNCED},
                table_key=TableKeys.ADMIN_CHECK_IN_EVENTS,
            )

            async def handle_edit(row, client) -> None:
                with client:
                    actor = await current_actor()
                    event = await service.get_event(row['id'])
                    if actor is None:
                        return
                    if event is None:
                        ui.notify("Couldn't find that event. Try refreshing.", color='warning')
                        return
                    await open_event_dialog(service, actor, on_done=_render_table.refresh, event=event)

            async def handle_remove(row, client) -> None:
                with client:
                    actor = await current_actor()

                    async def do_delete() -> None:
                        try:
                            await service.delete_event(actor, row['id'])
                        except (ValueError, PermissionError) as e:
                            notify_error(e)
                            return
                        ui.notify('Event deleted.', color='positive')
                        await _render_table.refresh()

                    ConfirmationDialog(
                        message=f"Delete {row['name']} and its whole roster, check-ins included?",
                        on_confirm=do_delete, confirm_text='Delete',
                    ).open()

            table.on('desk', lambda e: ui.navigate.to(f"/checkin/{e.args['id']}"))
            table.on('edit', lambda e: background_tasks.create(handle_edit(e.args, context.client)))
            table.on('remove', lambda e: background_tasks.create(handle_remove(e.args, context.client)))

        await _render_table()
