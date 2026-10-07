"""The Logging section of ``/platform``: per-module log levels at runtime.

A super-admin chasing a live problem turns one module up to DEBUG, reads the
container log, and turns it back down, with no redeploy. Levels persist across
restarts until cleared (see :class:`~application.services.LogLevelService`).
"""

from nicegui import ui

from application.services import LogLevelService
from application.utils.log_levels import LEVELS
from application.utils.timezone import format_local_display
from pages.platform_shared import current_actor
from theme.notify import notify_error
from theme.tables.mobile_grid import enable_mobile_grid
from theme.tables.preferences import TableKeys

_LEVEL_CHIP = '''
    <span class="wiz-chip" style="white-space:nowrap"
          :class="props.row.override ? 'wiz-chip--ok' : 'wiz-chip--neutral'">
        {{ props.row.override || 'inherit' }}
    </span>
'''

_ROW_ACTIONS = '''
    <q-btn dense flat color="primary" label="Set level"
           @click="$parent.$emit('set_level', props.row)" />
    <q-btn v-if="props.row.override" dense flat color="secondary" label="Reset"
           @click="$parent.$emit('reset_level', props.row)" />
'''


async def render_logging_section(user) -> None:
    """Build the logger table, wire its row actions, and load it."""
    with ui.row().classes('w-full items-center justify-between'):
        ui.label('Logging').classes('section-title')
        # Filled once the table exists; the header is drawn first.
        header_row = ui.row().classes('items-center')
    ui.label(
        'Set how much each part of the app writes to the container log. Changes '
        'apply immediately and survive restarts until you reset them. Sentry '
        'still gets errors as events and INFO and up as logs, whatever you pick '
        'here, so DEBUG and TRACE stay in the container log.'
    ).classes('text-caption text-grey')

    columns: list[dict] = [
        {'name': 'logger', 'label': 'Logger', 'field': 'logger', 'align': 'left', 'sortable': True},
        {'name': 'description', 'label': 'Covers', 'field': 'description', 'align': 'left'},
        {'name': 'override', 'label': 'Set to', 'field': 'override', 'align': 'left'},
        {'name': 'effective', 'label': 'Running at', 'field': 'effective', 'align': 'left'},
        {'name': 'updated', 'label': 'Changed', 'field': 'updated', 'align': 'left'},
        {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'right'},
    ]
    table = ui.table(columns=columns, rows=[], row_key='logger').classes('w-full wiz-table')
    table.add_slot('body-cell-override', f'<q-td :props="props">{_LEVEL_CHIP}</q-td>')
    table.add_slot('body-cell-actions', f'<q-td :props="props">{_ROW_ACTIONS}</q-td>')
    enable_mobile_grid(
        table, columns, actions=_ROW_ACTIONS,
        table_key=TableKeys.PLATFORM_LOG_LEVELS,
        field_slots={'override': _LEVEL_CHIP},
        wrap=True,
    )

    with header_row:
        ui.button(
            'Other logger', icon='add',
            on_click=lambda: _open_level_dialog(user, table, None),
        ).props('color=primary')

    async def _on_set(e) -> None:
        _open_level_dialog(user, table, e.args)

    async def _on_reset(e) -> None:
        await _reset(user, table, e.args)

    table.on('set_level', _on_set)
    table.on('reset_level', _on_reset)

    await _refresh(table)


async def _refresh(table) -> None:
    rows = await LogLevelService().list_rows(await current_actor())
    table.rows = [
        {
            'name': r.name,
            'logger': r.name or 'root',
            'description': r.description,
            'override': r.override or '',
            'effective': r.effective,
            'updated': (
                f'{format_local_display(r.updated_at)} by {r.updated_by or "unknown"}'
                if r.updated_at else '—'
            ),
        }
        for r in rows
    ]
    table.update()


def _open_level_dialog(actor, table, row) -> None:
    is_new = row is None
    with ui.dialog() as dialog, ui.card().classes('w-96 gap-2'):
        ui.label('Set a logger level' if is_new else f"Level for {row['logger']}").classes(
            'text-lg font-semibold')
        name = None
        if is_new:
            name = ui.input(
                'Logger name', placeholder='application.services.match.match_service',
            ).classes('w-full').props(
                'hint="The module path, as in logging.getLogger(__name__)"')
        level = ui.select(
            options=list(LEVELS), label='Level',
            value=(row or {}).get('override') or (row or {}).get('effective') or 'INFO',
        ).classes('w-full')

        async def submit() -> None:
            target = name.value if name is not None else row['name']
            try:
                await LogLevelService().set_level(actor, target, level.value)
            except (ValueError, PermissionError) as e:
                notify_error(e)
                return
            ui.notify(f"{(target or '').strip() or 'root'} now logs at {level.value}", color='positive')
            dialog.close()
            await _refresh(table)

        with ui.row().classes('w-full justify-end'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Apply', on_click=submit, color='primary')
    dialog.open()


async def _reset(actor, table, row) -> None:
    try:
        await LogLevelService().clear(actor, row['name'])
    except (ValueError, PermissionError) as e:
        notify_error(e)
        return
    ui.notify(f"{row['logger']} is back to inheriting its level", color='positive')
    await _refresh(table)
