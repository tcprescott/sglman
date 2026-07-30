"""Shared helpers for admin reports.

Defines the common filter strip (date range + tournament), CSV export
button, URL-state helpers, and a small page-shell wrapper.
"""

import json
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from nicegui import context, ui

from application.services import SystemConfigService, TournamentService
from application.utils.csv_export import rows_to_csv_bytes, timestamped_filename
from application.utils.timezone import EASTERN_TZ
from pages.admin_tabs.links import REPORTS, admin_url
from theme.tables.mobile_grid import enable_mobile_grid


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
    return admin_url(REPORTS, report=report, **params)


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


def show_navigating() -> None:
    """Acknowledge a click that is about to cost a full page navigation.

    Built as a NiceGUI element rather than ``ui.run_javascript``, which is
    deliberate: the outbox emits element *updates* before *messages* in a batch,
    so an element created here reaches the browser ahead of the ``open`` that
    navigates — a fire-and-forget ``run_javascript`` is deferred to a background
    task and loses that race.

    The overlay dies with the page, which is what is wanted: the next page
    renders fresh. Flagged on the client so a fast double-change is a no-op
    rather than a second overlay (never module state — one module is shared by
    every operator in every tenant).

    Filter changes no longer reach this — they re-render in place (see
    ``navigate_with_params``). It still covers the per-row drill-out, which is a
    real navigation to another admin tab.
    """
    client = context.client
    if getattr(client, '_wiz_report_navigating', False):
        return
    client._wiz_report_navigating = True
    with client.content:
        with ui.element('div').classes('wiz-report-busy'):
            with ui.element('div').classes('wiz-report-busy__box'):
                ui.spinner(size='sm')
                ui.label('Updating report…')


# Set per client (never module state — one module serves every operator in every
# tenant) by the Reports dispatcher, which owns the refreshable body.
_REFRESH_ATTR = '_wiz_report_refresh'


def _refresh_params(params: Mapping) -> dict:
    """Normalise filter params to what a real page load would have delivered.

    The refresh path has to agree with the reload path exactly, or a filter
    would mean one thing when clicked and another when the URL is opened. Two
    differences to close: ``admin_url`` drops ``None``/``''`` so the reload sees
    the handler's default, and it renders a ``date`` as ISO — which is what the
    route's ``start: str`` annotation would have produced. Ints are left alone,
    since the annotations (``tournament_id: int``, ``page: int``) coerce them
    and the handlers do arithmetic on them.
    """
    out: dict = {}
    for key, value in params.items():
        if value is None or value == '':
            continue
        out[key] = value.isoformat() if isinstance(value, (date, datetime)) else value
    return out


def bind_report_refresh(refresh: Callable[[Optional[str], dict], None]) -> None:
    """Register this client's in-place report re-render.

    Called once by the Reports dispatcher. Every filter handler in the subsystem
    goes through ``navigate_with_params``, so registering here is what turns all
    of them from a page reload into a refresh, without each report knowing.
    """
    setattr(context.client, _REFRESH_ATTR, refresh)


def navigate_with_params(report: Optional[str] = None, **params) -> None:
    """Apply new filter params to the Reports tab.

    Re-renders the report body in place and rewrites the URL with
    ``history.replaceState``, so the filters stay linkable and bookmarkable
    without the full navigation they used to cost. Falls back to a real
    navigation when no refreshable is bound — a report body rendered outside the
    dispatcher has nothing to refresh.
    """
    refresh = getattr(context.client, _REFRESH_ATTR, None)
    url = reports_url(report=report, **params)
    if refresh is None:
        show_navigating()
        ui.navigate.to(url)
        return
    # ``reports_url`` is root-relative and NiceGUI adds the client prefix when
    # *it* navigates; replaceState is ours, so the /t/<slug> prefix is ours to
    # add. Then hold the operator's scroll position across the rebuild: the body
    # is streamed in, so the document collapses mid-refresh and the browser
    # clamps scrollY unless something puts it back (static/js/report-nav.js).
    ui.run_javascript(
        f'history.replaceState(null, "", (window.path_prefix || "") + {json.dumps(url)});'
        'window.wizReportKeepPlace && window.wizReportKeepPlace();'
    )
    refresh(report, _refresh_params(params))


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
    href: Optional[str] = None,
    href_label: str = 'See the detail →',
) -> None:
    """A single flex KPI tile (title / big value / subtitle) for report strips.

    ``href`` turns the tile into a route to the report that explains the number
    — it must carry the same window the number was computed over, or the
    destination contradicts the tile it came from.
    """
    with ui.card().classes('q-pa-md').style(f'flex: 1 1 {min_width}px; min-width: {min_width}px;'):
        ui.label(title).classes('text-caption text-grey-7')
        ui.label(value).classes('text-h4').style(f'color: var(--q-{color});')
        ui.label(subtitle).classes('text-caption')
        if href:
            ui.link(href_label, href).classes('text-caption q-mt-xs')


# Per-row drill-out. Reports identify work; the surface that fixes it lives
# elsewhere, so a row carries an id there rather than growing its own mutation.
DRILL_FIELD = 'drill_url'
DRILL_HINT_FIELD = 'drill_hint'

# Both halves are static Vue: the destination arrives as row *data*
# (``props.row.drill_url``), never as markup templated into the slot. The button
# emits rather than rendering an ``<a href>`` — NiceGUI prepends the client's
# path prefix to a navigate target, so an anchor built in a template would drop
# the ``/t/<slug>`` in path-mode tenancy and 404.
_DRILL_CELL = r'''
        <q-td :props="props" class="text-right" @click.stop>
            <q-btn v-if="props.row.drill_url" flat dense round
                   icon="open_in_new" color="primary"
                   @click.stop="$parent.$emit('drill', props.row)">
                <q-tooltip>{{ props.row.drill_hint }}</q-tooltip>
            </q-btn>
        </q-td>
'''
# The card mirror. enable_mobile_grid builds its card body from the columns and
# skips the actions column entirely, so a cell slot alone is invisible on a
# phone — this is what makes the control exist there.
_DRILL_ACTION = r'''
            <q-btn v-if="props.row.drill_url" flat dense
                   icon="open_in_new" color="primary"
                   :label="props.row.drill_hint"
                   @click.stop="$parent.$emit('drill', props.row)" />
'''


def enable_drill_link(
    table: ui.table,
    columns: Sequence[Mapping],
    rows: Sequence[dict],
    url_for: Callable[[Mapping], Optional[str]],
    *,
    enabled: bool = True,
    hint: str = 'Open on the schedule board',
) -> str:
    """Add a per-row navigating control to ``table``; return its card mirror.

    Call after building the table and pass the return value as
    ``enable_mobile_grid(..., actions=…)`` — the desktop cell and the card
    footer are one call so they cannot be shipped apart.

    ``url_for`` returns the destination for a row, or ``None`` for a row with
    nowhere to go (its cell stays empty). ``enabled`` is the destination's own
    authorization predicate: when it is false the column is not rendered at all
    rather than rendered disabled, because a control that is present and
    refuses is worse than one that was never offered.

    The caller's ``columns`` list is left untouched, so a CSV export built from
    it does not grow a URL column.
    """
    if not enabled:
        return ''

    for row in rows:
        row[DRILL_FIELD] = url_for(row) or ''
        row[DRILL_HINT_FIELD] = hint

    table.columns = [
        *columns,
        {'name': 'drill', 'label': '', 'field': DRILL_FIELD, 'align': 'right'},
    ]
    # Re-assign, don't rely on the mutation above reaching the client: NiceGUI
    # copies rows into ObservableDicts when the table is built, so the caller's
    # dicts and ``table.rows`` are different objects from that point on.
    table.rows = rows
    table.add_slot('body-cell-drill', _DRILL_CELL)
    table.on('drill', _follow_drill)
    return _DRILL_ACTION


def _follow_drill(e) -> None:
    url = clicked_row(e).get(DRILL_FIELD)
    if url:
        # Same acknowledgment a filter change gets: this is a full navigation
        # to another admin tab, not an in-page update.
        show_navigating()
        ui.navigate.to(url)


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


def _page_range_label(total: int, page: int, page_size: int, noun: str) -> str:
    """``Showing 51–100 of 124 entries`` — or just ``124 entries`` on one page.

    The header used to be handed a pre-formatted count, so it read ``124
    entries`` above a table paginated to 50. Both numbers were true and together
    they were misleading: what you are reading is a page, and nothing said so.
    """
    if total <= page_size:
        return f'{total:,} {noun}'
    first = (page - 1) * page_size + 1
    if first > total:
        # A hand-edited ``?page=`` past the end. Saying "Showing 101–95" would
        # be worse than saying nothing about the range.
        return f'{total:,} {noun} — page {page} is past the end'
    last = min(page * page_size, total)
    return f'Showing {first:,}–{last:,} of {total:,} {noun}'


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
    count_noun: str,
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
            ui.label(_page_range_label(total, page, page_size, count_noun)).classes('text-h6')
            csv_export_button(csv_filename_prefix, lambda: columns, lambda: rows)

        table = ui.table(columns=columns, rows=rows, row_key=row_key).classes('full-width')
        table.add_slot('body', _EVENT_LOG_BODY_ROWCLICK if on_row_click else _EVENT_LOG_BODY_PLAIN)
        if on_row_click is not None:
            table.on('row-click', lambda e: on_row_click(clicked_row(e)))
        enable_mobile_grid(table, columns, row_click_event='row-click' if on_row_click else None)
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
