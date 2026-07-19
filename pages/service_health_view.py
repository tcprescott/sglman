"""Shared service-health board rendering (PR 5).

One ``@ui.refreshable`` table of dependency statuses, reused by the platform
board (full, refreshable) and the tenant admin tab (read-only subset). Colored
status badges make an outage or credential warning scannable at a glance.
"""

from typing import Callable, List, Optional

from nicegui import background_tasks, context, ui

from application.services import ProbeResult, ServiceStatus
from application.utils.timezone import format_eastern_display

_STATUS_COLOR = {
    ServiceStatus.HEALTHY: 'positive',
    ServiceStatus.DEGRADED: 'orange',
    ServiceStatus.CREDENTIAL_WARNING: 'amber-8',
    ServiceStatus.DOWN: 'negative',
    ServiceStatus.UNKNOWN: 'grey',
}

_STATUS_LABEL = {
    ServiceStatus.HEALTHY: 'Healthy',
    ServiceStatus.DEGRADED: 'Degraded',
    ServiceStatus.CREDENTIAL_WARNING: 'Credential warning',
    ServiceStatus.DOWN: 'Down',
    ServiceStatus.UNKNOWN: 'Unknown',
}

_COLUMNS = [
    {'name': 'label', 'label': 'Dependency', 'field': 'label', 'align': 'left', 'sortable': True},
    {'name': 'category', 'label': 'Category', 'field': 'category', 'align': 'left', 'sortable': True},
    {'name': 'status', 'label': 'Status', 'field': 'status', 'align': 'left'},
    {'name': 'message', 'label': 'Detail', 'field': 'message', 'align': 'left'},
    {'name': 'checked_at', 'label': 'Checked', 'field': 'checked_at', 'align': 'left'},
]


def _rows(results: List[ProbeResult]) -> List[dict]:
    return [
        {
            'label': r.label,
            'category': r.category,
            'status': _STATUS_LABEL[r.status],
            'status_color': _STATUS_COLOR[r.status],
            'message': r.message,
            # App-wide convention: display US/Eastern, never raw UTC.
            'checked_at': format_eastern_display(r.checked_at),
        }
        for r in results
    ]


def render_health_table(results: List[ProbeResult]) -> None:
    """Render the status table for a set of probe results (no controls)."""
    if not results:
        ui.label('No dependencies to report.').classes('text-caption text-grey')
        return
    table = ui.table(columns=_COLUMNS, rows=_rows(results), row_key='label').classes(
        'w-full sgl-table').props(':grid="Quasar.Screen.lt.md"')
    table.add_slot('body-cell-status', '''
        <q-td :props="props">
            <q-badge :color="props.row.status_color" :label="props.value" />
        </q-td>
    ''')
    # Mobile card (below Quasar's lt.md breakpoint) — the desktop columns overflow
    # a phone viewport, so each dependency renders as a stacked card instead.
    table.add_slot('item', '''
        <div class="q-pa-xs col-xs-12 col-sm-6">
            <q-card bordered flat class="q-pa-sm sgl-grid-card">
                <div class="row items-center justify-between no-wrap q-mb-xs">
                    <div class="text-weight-bold">{{ props.row.label }}</div>
                    <q-badge :color="props.row.status_color" :label="props.row.status" />
                </div>
                <div class="text-caption text-grey-7 q-mb-xs">{{ props.row.category }}</div>
                <div v-if="props.row.message" class="q-mb-xs" style="overflow-wrap:anywhere">{{ props.row.message }}</div>
                <div class="text-caption text-grey-7">Checked {{ props.row.checked_at }}</div>
            </q-card>
        </div>
    ''')


def build_refreshable_board(
    initial_loader: Callable[[], 'object'],
    *,
    refresh_loader: Optional[Callable[[], 'object']] = None,
) -> None:
    """Render a health board that loads its rows in the background.

    ``initial_loader`` (a coroutine → list[ProbeResult]) supplies the rows shown on
    mount — typically the cached snapshot, so the page paints instantly. When
    ``refresh_loader`` is given, a "Refresh now" button re-runs it (a live re-probe)
    and repaints. Both are called off the render path so a slow probe never blocks
    the page.
    """
    state: dict = {'results': []}
    # Captured at render time (valid slot context); restored inside the background
    # tasks below, where the slot stack is otherwise empty.
    client = context.client

    @ui.refreshable
    def board() -> None:
        render_health_table(state['results'])

    async def _load(loader: Callable[[], 'object'], *, notify: bool) -> None:
        results = list(await loader())
        state['results'] = results
        with client:
            board.refresh()
            if notify:
                ui.notify('Health refreshed', color='positive')

    if refresh_loader is not None:
        ui.button('Refresh now', icon='refresh',
                  on_click=lambda: background_tasks.create(_load(refresh_loader, notify=True)))

    board()
    background_tasks.create(_load(initial_loader, notify=False))
