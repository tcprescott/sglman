"""Admin Webhooks Page — staff-managed outbound webhooks."""

import json

from nicegui import app, background_tasks, context, ui
from theme.notify import notify_error

from application.events import EventType
from application.services import WebhookService, get_user_from_discord_id
from application.utils.timezone import format_eastern_display

# Event-type options for the multiselect. '*' (all events) is offered first.
_EVENT_OPTIONS = {EventType.WILDCARD: 'All events (*)'}
_EVENT_OPTIONS.update({name: name for name in sorted(EventType.ALL)})

# Receiver-side verification snippet shown in the payload-format reference.
_SIGNATURE_SNIPPET = '''import hmac, hashlib

signed = f"{request.headers['X-SGL-Timestamp']}.{raw_body}".encode()
expected = "sha256=" + hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
assert hmac.compare_digest(expected, request.headers["X-SGL-Signature"])'''


def _render_format_reference() -> None:
    """A collapsed, code-derived reference for what the app POSTs to a receiver."""
    ref = WebhookService.format_reference()
    with ui.expansion('Webhook payload & event reference', icon='description').classes('w-full'):
        ui.label(
            'When a subscribed event occurs, the app sends an HTTP POST to your URL with '
            'this JSON body (keys are sorted for a stable signature):'
        ).classes('text-caption text-grey')
        ui.code(json.dumps(ref['example_payload'], indent=2), language='json').classes('w-full')

        ui.label('Headers').classes('text-subtitle2 q-mt-md')
        ui.table(
            columns=[
                {'name': 'name', 'label': 'Header', 'field': 'name', 'align': 'left'},
                {'name': 'description', 'label': 'Meaning', 'field': 'description', 'align': 'left'},
            ],
            rows=ref['headers'],
            row_key='name',
        ).props('flat dense').classes('w-full')

        ui.label('Verify the signature (receiver side)').classes('text-subtitle2 q-mt-md')
        ui.code(_SIGNATURE_SNIPPET, language='python').classes('w-full')

        c = ref['constants']
        ui.label(
            f"Delivery runs off the request path with a {c['timeout_seconds']:.0f}s timeout, "
            f"up to {c['max_attempts']} attempts with exponential backoff "
            f"({c['backoff_base']}**attempt seconds) on any non-2xx or transport error. "
            'Each attempt is recorded (see Recent deliveries).'
        ).classes('text-caption text-grey q-mt-md')

        ui.label('Events').classes('text-subtitle2 q-mt-md')
        ui.label(
            f"Subscribe to specific events, or '{ref['wildcard']}' for all:"
        ).classes('text-caption text-grey')
        with ui.column().classes('gap-0'):
            for group, names in ref['events'].items():
                with ui.row().classes('items-baseline gap-2'):
                    ui.label(f'{group}.').classes('text-weight-medium')
                    ui.label(', '.join(names)).classes('text-caption text-grey')

        ui.label(
            'Security: URLs must be https:// (SSRF-guarded in production); the signing secret '
            'is shown only once and is never returned by the API or written to logs.'
        ).classes('text-caption text-grey q-mt-md')


def _events_summary(event_types) -> str:
    if not event_types:
        return '—'
    if EventType.WILDCARD in event_types:
        return 'All events'
    return ', '.join(event_types)


async def admin_webhooks_page() -> None:
    service = WebhookService()

    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('Webhooks').classes('page-title')

        ui.separator().classes('separator-spacing')

        ui.label(
            'Send a signed JSON POST to an external URL when the selected events occur. '
            'Each request carries an X-SGL-Signature (HMAC-SHA256 of the body using the '
            "webhook's secret). The secret is shown only once, when created or rotated."
        ).classes('text-caption text-grey')

        _render_format_reference()

        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id', 'hidden': True},
            {'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True},
            {'name': 'url', 'label': 'URL', 'field': 'url'},
            {'name': 'events', 'label': 'Events', 'field': 'events'},
            {'name': 'is_active', 'label': 'Active', 'field': 'is_active', 'sortable': True},
            {'name': 'actions', 'label': '', 'field': 'actions'},
        ]

        table_container = ui.column().classes('w-full')

        async def refresh_table():
            webhooks = await service.list_webhooks(await _current())
            table.rows = [
                {
                    'id': w.id,
                    'name': w.name,
                    'url': w.url,
                    'events': _events_summary(w.event_types),
                    'is_active': 'Yes' if w.is_active else 'No',
                    'event_types': w.event_types,
                    'is_active_raw': w.is_active,
                }
                for w in webhooks
            ]
            table.update()

        async def _current():
            return await get_user_from_discord_id(app.storage.user.get('discord_id'))

        def show_secret(title: str, secret: str) -> None:
            with ui.dialog() as dialog, ui.card().classes('w-96'):
                ui.label(title).classes('text-h6')
                ui.label('Copy this secret now — it will not be shown again.').classes('text-caption text-warning')
                ui.input(value=secret).props('readonly outlined').classes('w-full')
                with ui.row().classes('justify-end w-full'):
                    ui.button('Done', on_click=dialog.close).props('color=primary')
            dialog.open()

        async def delete_webhook(row, client):
            with client:
                try:
                    await service.delete_webhook(await _current(), row['id'])
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                ui.notify('Webhook deleted', color='positive')
                await refresh_table()

        async def regenerate_secret(row, client):
            with client:
                try:
                    secret = await service.regenerate_secret(await _current(), row['id'])
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                show_secret('New signing secret', secret)

        async def view_deliveries(row, client):
            with client:
                try:
                    deliveries = await service.list_deliveries(await _current(), row['id'])
                except (ValueError, PermissionError) as e:
                    notify_error(e)
                    return
                with ui.dialog() as dialog, ui.card().classes('w-[36rem]'):
                    ui.label(f"Recent deliveries — {row['name']}").classes('text-h6')
                    if not deliveries:
                        ui.label('No deliveries yet.').classes('text-grey')
                    else:
                        rows = [
                            {
                                'event': d.event_type,
                                'status': '✓' if d.success else '✗',
                                'code': d.response_status if d.response_status is not None else '—',
                                'attempts': d.attempt_count,
                                'when': format_eastern_display(d.created_at) if d.created_at else '',
                                'error': d.error or '',
                            }
                            for d in deliveries
                        ]
                        ui.table(
                            columns=[
                                {'name': 'when', 'label': 'When', 'field': 'when'},
                                {'name': 'event', 'label': 'Event', 'field': 'event'},
                                {'name': 'status', 'label': 'OK', 'field': 'status'},
                                {'name': 'code', 'label': 'HTTP', 'field': 'code'},
                                {'name': 'attempts', 'label': 'Tries', 'field': 'attempts'},
                                {'name': 'error', 'label': 'Error', 'field': 'error'},
                            ],
                            rows=rows,
                            row_key='when',
                        ).classes('w-full')
                    with ui.row().classes('justify-end w-full'):
                        ui.button('Close', on_click=dialog.close).props('flat')
                dialog.open()

        def open_webhook_dialog(existing=None) -> None:
            is_edit = existing is not None
            with table_container:
                with ui.dialog() as dialog, ui.card().classes('w-96'):
                    ui.label('Edit Webhook' if is_edit else 'Add Webhook').classes('text-h6')
                    name_input = ui.input(
                        'Name', value=existing['name'] if is_edit else '',
                    ).classes('w-full')
                    url_input = ui.input(
                        'URL', value=existing['url'] if is_edit else '',
                        placeholder='https://example.com/hook',
                    ).classes('w-full')
                    events_select = ui.select(
                        options=_EVENT_OPTIONS,
                        label='Events',
                        multiple=True,
                        value=existing['event_types'] if is_edit else [],
                    ).props('use-chips').classes('w-full')
                    active_switch = ui.switch(
                        'Active', value=existing['is_active_raw'] if is_edit else True,
                    )

                    async def submit():
                        events = list(events_select.value or [])
                        try:
                            current = await _current()
                            if is_edit:
                                await service.update_webhook(
                                    current, existing['id'],
                                    name=name_input.value,
                                    url=url_input.value,
                                    event_types=events,
                                    is_active=active_switch.value,
                                )
                                dialog.close()
                                ui.notify('Webhook updated', color='positive')
                                await refresh_table()
                            else:
                                webhook = await service.create_webhook(
                                    current,
                                    name=name_input.value,
                                    url=url_input.value,
                                    event_types=events,
                                    is_active=active_switch.value,
                                )
                                dialog.close()
                                await refresh_table()
                                show_secret('Webhook created — signing secret', webhook.secret)
                        except (ValueError, PermissionError) as e:
                            notify_error(e)

                    with ui.row().classes('justify-end w-full'):
                        ui.button('Cancel', on_click=dialog.close).props('flat')
                        ui.button(
                            'Save' if is_edit else 'Add', icon='save' if is_edit else 'add',
                            on_click=submit,
                        ).props('color=primary')
            dialog.open()

        with table_container:
            with ui.row().classes('full-width'):
                ui.button('Add Webhook', icon='add', on_click=lambda: open_webhook_dialog()).props('color=primary')
                ui.space()
                ui.button(
                    icon='refresh', on_click=lambda: background_tasks.create(refresh_table()),
                ).props('flat color=primary').tooltip('Refresh table')

            table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full')

            table.add_slot('body-cell-actions', '''
                <q-td :props="props">
                    <q-btn flat round dense icon="edit" color="primary"
                           @click="$parent.$emit('edit', props.row)">
                        <q-tooltip>Edit</q-tooltip>
                    </q-btn>
                    <q-btn flat round dense icon="vpn_key" color="primary"
                           @click="$parent.$emit('regenerate', props.row)">
                        <q-tooltip>Regenerate secret</q-tooltip>
                    </q-btn>
                    <q-btn flat round dense icon="history" color="primary"
                           @click="$parent.$emit('deliveries', props.row)">
                        <q-tooltip>Recent deliveries</q-tooltip>
                    </q-btn>
                    <q-btn flat round dense icon="delete" color="negative"
                           @click="$parent.$emit('delete', props.row)">
                        <q-tooltip>Delete</q-tooltip>
                    </q-btn>
                </q-td>
            ''')

            table.on('edit', lambda e: open_webhook_dialog(e.args))
            table.on('regenerate', lambda e: background_tasks.create(regenerate_secret(e.args, context.client)))
            table.on('deliveries', lambda e: background_tasks.create(view_deliveries(e.args, context.client)))
            table.on('delete', lambda e: background_tasks.create(delete_webhook(e.args, context.client)))

        ui.on('selected_tab', lambda e: background_tasks.create(refresh_table()) if e.args == 'Webhooks' else None)
        background_tasks.create(refresh_table())
