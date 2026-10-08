"""Admin → Check-in: set up the events the check-in desk runs (Staff).

Each event names a Matcherino venue whose badge sales become the desk's
roster. Opening an event puts it on the desk and starts the background sync;
the desk itself lives at ``/checkin``.

The Matcherino login card above the events holds the refresh token the sync
signs in with. It is **write-only**: the saved token is never rendered back,
only whose account it is and when it was saved.
"""

from nicegui import background_tasks, context, ui

from application.services import CheckInService, MatcherinoLoginService
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
    {'name': 'venue', 'label': 'Matcherino venue', 'field': 'venue', 'align': 'left'},
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
    comps = bool(event.comp_roles) or event.comp_volunteers
    if event.matcherino_venue_id is None and not comps:
        return 'Walk-ups only'
    if event.matcherino_venue_id is None and event.last_synced_at is None:
        return 'Comps only · not synced yet'
    if event.matcherino_venue_id is None:
        return f'Comps only · {format_local_display(event.last_synced_at)}'
    if event.last_sync_error:
        return f'Failed: {event.last_sync_error}'
    if event.last_synced_at is None:
        return 'Not yet'
    return f'{format_local_display(event.last_synced_at)} · {event.last_sync_count or 0} with badges'


_LOGIN_STEPS = (
    'Sign in to matcherino.com as an account that is an admin of your venue.',
    'Open DevTools (F12), switch to the Network tab and reload the page.',
    'Select the "token" request to api.matcherino.com, open its Payload, and copy '
    'refreshToken. Pasting the whole payload works too.',
)


async def _matcherino_login_card() -> None:
    service = MatcherinoLoginService()

    async def save(token_input, client) -> None:
        with client:
            actor = await current_actor()
            if actor is None:
                return
            try:
                status = await service.set_login(actor, token_input.value)
            except (ValueError, PermissionError) as e:
                notify_error(e)
                return
            token_input.value = ''
            account = f' as account #{status.matcherino_user_id}' if status.matcherino_user_id else ''
            ui.notify(f'Matcherino accepted the token. Ticket sync now signs in{account}.',
                      color='positive')
            login_section.refresh()

    async def remove(client) -> None:
        with client:
            actor = await current_actor()

            async def do_remove() -> None:
                try:
                    await service.clear_login(actor)
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify('Matcherino login removed.', color='positive')
                login_section.refresh()

            ConfirmationDialog(
                message="Remove the saved Matcherino login? Ticket sync stops until someone adds a new one.",
                on_confirm=do_remove, confirm_text='Remove',
            ).open()

    @ui.refreshable
    async def login_section() -> None:
        try:
            status = await service.status(await current_actor())
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        with ui.card().classes('w-full'):
            ui.label('Matcherino login').classes('text-subtitle2 text-bold')
            if status.configured:
                account = (f'Matcherino account #{status.matcherino_user_id}'
                           if status.matcherino_user_id else 'A Matcherino account')
                saved = format_local_display(status.updated_at) if status.updated_at else 'an unknown time'
                by = f' by {status.updated_by}' if status.updated_by else ''
                ui.label(f'{account} · saved {saved}{by}').classes('text-caption text-positive')
            else:
                ui.label(
                    "Not set. Ticket sync can't read your venue's badge sales until you add one."
                ).classes('text-caption text-warning')
            with ui.row().classes('items-center w-full no-wrap'):
                token_input = ui.input('Refresh token').props(
                    'type=password autocomplete=off dense outlined'
                ).classes('flex-grow')
                if status.configured:
                    token_input.props('hint="Saving a new token replaces the one stored"')
                ui.button(
                    'Save', icon='save',
                    on_click=lambda: background_tasks.create(save(token_input, context.client)),
                ).props('color=primary dense').classes(REQUIRES_SOCKET_CLASS)
                if status.configured:
                    ui.button(
                        'Remove', icon='delete',
                        on_click=lambda: background_tasks.create(remove(context.client)),
                    ).props('flat color=negative dense').classes(REQUIRES_SOCKET_CLASS)
            with ui.expansion('Where do I get one?').classes('w-full text-caption'):
                for number, step in enumerate(_LOGIN_STEPS, start=1):
                    ui.label(f'{number}. {step}').classes('text-caption')
                ui.label(
                    "Treat it like a password: whoever holds it is that Matcherino account. "
                    "When Matcherino stops accepting it, the desk shows the sync failing; "
                    "paste a fresh one here."
                ).classes('text-caption text-grey-7')

    await login_section()


async def admin_check_in_page() -> None:
    service = CheckInService()

    with ui.column().classes('page-container-narrow w-full'):
        with ui.row().classes('header-row'):
            ui.label('Check-in').classes('page-title')
        ui.label(
            "Each event pulls its roster from a Matcherino venue's badge sales. Open an "
            'event to put it on the check-in desk; the desk syncs on its own while it is open.'
        ).classes('text-caption text-grey-7')
        ui.separator().classes('separator-spacing')

        await _matcherino_login_card()

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
                    'venue': str(e.matcherino_venue_id) if e.matcherino_venue_id else '—',
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
