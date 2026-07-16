"""Shared helpers for admin reports.

Defines the common filter strip (date range + tournament), CSV export
button, URL-state helpers, and a small page-shell wrapper.
"""

import json
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence
from urllib.parse import urlencode

from nicegui import ui

from application.services import SystemConfigService, TournamentService
from application.utils.csv_export import rows_to_csv_bytes, timestamped_filename
from application.utils.timezone import EASTERN_TZ


REPORT_KEYS = ('capacity', 'match_ops', 'crew', 'stream_rooms', 'audit')

# ECharts series palette. Canvas charts can't read CSS var() tokens and are
# painted once server-side, so these are fixed mid-tone steps of the phoenix
# hues chosen to hold ≥3:1 contrast on BOTH the light and dark card surfaces
# (validated against #FFFFFF and #241e19). Assign by role — never per-chart:
CHART_GOLD = '#B5791C'     # primary series (brand gold, mid step)
CHART_TEAL = '#17A097'     # secondary series (status-live hue)
CHART_RED = '#C94E3D'      # thresholds/limits (status-cancelled hue)
CHART_NEUTRAL = '#8D8379'  # absence/idle series (warm gray — reads gray by design)
CHART_GOLD_AREA = 'rgba(181, 121, 28, 0.18)'  # CHART_GOLD at 18% for area fills

# Chart chrome. ECharts' default axis/legend grays assume a white canvas and
# go illegible in dark mode; these sit at the equal-contrast point between the
# light and dark surfaces (~4:1 against both), the best a single value can do.
CHART_TEXT = '#877D72'                       # axis labels, axis names, legend
CHART_GRID = 'rgba(135, 125, 114, 0.35)'     # gridlines/axis lines — recessive on both


def themed_chart_option(option: dict) -> dict:
    """Overlay the mode-neutral chrome colors onto an ECharts option in place.

    Sets default text, legend text, and per-axis label/name/line/split-line
    colors without clobbering anything the chart already specifies.
    """
    option.setdefault('textStyle', {}).setdefault('color', CHART_TEXT)
    if 'legend' in option:
        option['legend'].setdefault('textStyle', {}).setdefault('color', CHART_TEXT)
    if 'toolbox' in option:
        option['toolbox'].setdefault('iconStyle', {}).setdefault('borderColor', CHART_TEXT)
    for key in ('xAxis', 'yAxis'):
        axes = option.get(key)
        if axes is None:
            continue
        for axis in axes if isinstance(axes, list) else [axes]:
            axis.setdefault('axisLabel', {}).setdefault('color', CHART_TEXT)
            axis.setdefault('nameTextStyle', {}).setdefault('color', CHART_TEXT)
            axis.setdefault('axisLine', {}).setdefault('lineStyle', {}).setdefault('color', CHART_GRID)
            axis.setdefault('splitLine', {}).setdefault('lineStyle', {}).setdefault('color', CHART_GRID)
    return option


def reports_url(report: Optional[str] = None, **params) -> str:
    """Build an ``/admin/reports[?report=…&…]`` URL preserving filters.

    The Reports section is a path segment (``/admin/reports``); the report name
    and its filters stay query params, since they are orthogonal report state."""
    payload: dict = {}
    if report:
        payload['report'] = report
    for key, value in params.items():
        if value is None or value == '':
            continue
        if isinstance(value, (date, datetime)):
            payload[key] = value.isoformat()
        else:
            payload[key] = value
    return '/admin/reports?' + urlencode(payload) if payload else '/admin/reports'


def parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return None


def parse_int(value) -> Optional[int]:
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def eastern_bounds(start_d: date, end_d: date) -> tuple[datetime, datetime]:
    """Convert a Eastern date range to half-open aware datetime bounds."""
    if end_d < start_d:
        end_d = start_d
    start = datetime.combine(start_d, time(0, 0), tzinfo=EASTERN_TZ)
    end = datetime.combine(end_d + timedelta(days=1), time(0, 0), tzinfo=EASTERN_TZ)
    return start, end


async def default_date_range(
    start_param: Optional[str],
    end_param: Optional[str],
) -> tuple[date, date]:
    if start_param and end_param:
        s = parse_date(start_param)
        e = parse_date(end_param)
        if s and e:
            return s, e
    return await SystemConfigService.get_event_window()


@contextmanager
def report_page_shell(title: str, back_to_dashboard: bool = True):
    """Render a report-detail title bar with an optional back-to-dashboard link."""
    with ui.column().classes('page-container-wide'):
        with ui.row().classes('header-row items-center'):
            if back_to_dashboard:
                ui.link('← Reports', reports_url()).classes('text-sm')
            ui.label(title).classes('page-title')
        ui.separator().classes('separator-spacing')
        yield


def date_range_filter(
    default_start: date,
    default_end: date,
    on_change: Callable[[date, date], None],
) -> tuple[ui.input, ui.input]:
    """Render a Start/End date pair. Calls ``on_change`` when either changes."""
    state = {'start': default_start, 'end': default_end}

    def _fire():
        on_change(state['start'], state['end'])

    with ui.row().classes('items-end gap-3'):
        start_input = ui.input('Start date', value=default_start.isoformat()).props('dense')
        with ui.menu().props('no-parent-event') as start_menu:
            start_picker = ui.date(value=default_start.isoformat()).bind_value(start_input)
            with ui.row().classes('justify-end'):
                ui.button('OK', on_click=start_menu.close).props('flat dense')
        with start_input.add_slot('append'):
            ui.icon('edit_calendar').on('click', start_menu.open).classes('cursor-pointer')

        end_input = ui.input('End date', value=default_end.isoformat()).props('dense')
        with ui.menu().props('no-parent-event') as end_menu:
            end_picker = ui.date(value=default_end.isoformat()).bind_value(end_input)
            with ui.row().classes('justify-end'):
                ui.button('OK', on_click=end_menu.close).props('flat dense')
        with end_input.add_slot('append'):
            ui.icon('edit_calendar').on('click', end_menu.open).classes('cursor-pointer')

    def _on_start(e):
        parsed = parse_date(start_input.value)
        if parsed:
            state['start'] = parsed
            _fire()

    def _on_end(e):
        parsed = parse_date(end_input.value)
        if parsed:
            state['end'] = parsed
            _fire()

    start_input.on('change', _on_start)
    end_input.on('change', _on_end)
    start_picker.on('update:model-value', lambda e: _on_start(e))
    end_picker.on('update:model-value', lambda e: _on_end(e))
    return start_input, end_input


async def tournament_filter(
    current_id: Optional[int],
    on_change: Callable[[Optional[int]], None],
) -> ui.select:
    tournaments = await TournamentService().get_all_tournaments()
    options: dict = {0: 'All tournaments'}
    for t in tournaments:
        options[t.id] = t.name
    value = current_id if current_id and current_id in options else 0
    select = ui.select(
        options=options,
        value=value,
        label='Tournament',
    ).classes('control-width').props('dense')

    def _on_change(_e):
        v = select.value
        on_change(int(v) if v else None)

    select.on('update:model-value', _on_change)
    return select


def csv_export_button(
    filename_prefix: str,
    columns_provider: Callable[[], Sequence[Mapping]],
    rows_provider: Callable[[], Iterable[Mapping]],
    label: str = 'Export CSV',
) -> ui.button:
    """Button that downloads the current rows as CSV when clicked."""

    def _click():
        try:
            data = rows_to_csv_bytes(columns_provider(), rows_provider())
            ui.download(data, filename=timestamped_filename(filename_prefix))
        except Exception as exc:  # pragma: no cover - defensive UI feedback
            ui.notify(f'Export failed: {exc}', color='negative')

    return ui.button(label, icon='download', on_click=_click).props('flat dense')


def navigate_with_params(report: Optional[str] = None, **params) -> None:
    """Reload the admin page with new query params (used for filter changes)."""
    ui.navigate.to(reports_url(report=report, **params))


def parse_details(raw: Optional[str]) -> tuple[Optional[Any], str]:
    """Return ``(parsed_json_or_none, display_text)`` for an audit/telemetry blob.

    Legacy rows store plain-text details — those parse to None and display
    as-is. New rows store JSON and display pretty-printed.
    """
    if not raw:
        return None, ''
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None, raw
    if parsed is None:
        return None, ''
    if isinstance(parsed, (dict, list)):
        return parsed, json.dumps(parsed, indent=2, sort_keys=True)
    return parsed, str(parsed)


def kpi_card(
    title: str,
    value: str,
    subtitle: str,
    color: str = 'primary',
    min_width: int = 220,
) -> None:
    """A single flex KPI tile (title / big value / subtitle) for report strips."""
    with ui.card().classes('q-pa-md').style(f'flex: 1 1 {min_width}px; min-width: {min_width}px;'):
        ui.label(title).classes('text-caption text-grey-7')
        ui.label(value).classes('text-h4').style(f'color: var(--q-{color});')
        ui.label(subtitle).classes('text-caption')


def clicked_row(e) -> dict:
    """Extract the row dict from a NiceGUI table ``row-click`` event.

    Body-slot templates emit ``$event, props.row`` (args ``[evt, row]``); a bare
    table emits the row directly. Return ``{}`` when neither yields a dict.
    """
    args = e.args
    row = args[1] if isinstance(args, list) and len(args) > 1 else args
    return row if isinstance(row, dict) else {}


# Expandable-details ``body`` slot for event-log tables. The ``details`` column
# renders a collapsible pretty-printed JSON cell; every other column is plain.
# Two variants: one emits ``row-click`` for a drill-down filter, one does not.
_EVENT_LOG_DETAILS_CELL = r'''
        <q-td v-for="col in props.cols" :key="col.name" :props="props">
            <template v-if="col.name !== 'details'">
                {{ col.value }}
            </template>
            <div v-else @click.stop>
                <q-expansion-item
                    v-if="props.row.full_details && props.row.full_details.length > 0"
                    dense dense-toggle switch-toggle-side
                    :label="props.row.details"
                    class="text-body2"
                >
                    <pre class="q-mt-xs q-pa-sm bg-grey-2 text-body2" style="white-space: pre-wrap;">{{ props.row.full_details }}</pre>
                </q-expansion-item>
                <span v-else class="text-grey-7">—</span>
            </div>
        </q-td>
'''
_EVENT_LOG_BODY_ROWCLICK = (
    r'''<q-tr :props="props" @click="$parent.$emit('row-click', $event, props.row)" style="cursor: pointer">'''
    + _EVENT_LOG_DETAILS_CELL + '</q-tr>'
)
_EVENT_LOG_BODY_PLAIN = r'<q-tr :props="props">' + _EVENT_LOG_DETAILS_CELL + '</q-tr>'


def paginated_event_log(
    *,
    columns: Sequence[Mapping],
    rows: Sequence[Mapping],
    row_key: str,
    total: int,
    page: int,
    page_size: int,
    on_page: Callable[[int], None],
    csv_filename_prefix: str,
    count_label: str,
    note: str,
    on_row_click: Optional[Callable[[dict], None]] = None,
    card_classes: str = 'full-width q-pa-md',
) -> None:
    """Server-paginated event-log card (count + CSV + expandable table + pager).

    Shared by the Audit Log and Engagement Telemetry reports. ``on_row_click``,
    when given, wires a per-row drill-down filter (receives the clicked row
    dict); ``on_page`` reloads the page for a new 1-based page number.
    """
    with ui.card().classes(card_classes):
        with ui.row().classes('items-center justify-between full-width'):
            ui.label(count_label).classes('text-h6')
            csv_export_button(csv_filename_prefix, lambda: columns, lambda: rows)

        table = ui.table(columns=columns, rows=rows, row_key=row_key).classes('full-width')
        table.add_slot('body', _EVENT_LOG_BODY_ROWCLICK if on_row_click else _EVENT_LOG_BODY_PLAIN)
        if on_row_click is not None:
            table.on('row-click', lambda e: on_row_click(clicked_row(e)))
        ui.label(note).classes('italic-note')

        total_pages = max(1, (total + page_size - 1) // page_size)
        with ui.row().classes('items-center q-mt-sm'):
            ui.label(f'Page {page} of {total_pages}').classes('text-caption')
            ui.button(
                'Previous', icon='chevron_left',
                on_click=lambda: on_page(page - 1),
            ).props('flat dense').set_enabled(page > 1)
            ui.button(
                'Next', icon='chevron_right',
                on_click=lambda: on_page(page + 1),
            ).props('flat dense').set_enabled(page < total_pages)
