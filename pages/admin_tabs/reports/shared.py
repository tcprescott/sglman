"""Shared helpers for admin reports.

Defines the common filter strip (date range + tournament), CSV export
button, URL-state helpers, and a small page-shell wrapper.
"""

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from typing import Callable, Iterable, Mapping, Optional, Sequence
from urllib.parse import urlencode

from nicegui import background_tasks, ui

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


def reports_url(report: Optional[str] = None, **params) -> str:
    """Build an ``/admin?tab=Reports[&report=…&…]`` URL preserving filters."""
    payload: dict = {'tab': 'Reports'}
    if report:
        payload['report'] = report
    for key, value in params.items():
        if value is None or value == '':
            continue
        if isinstance(value, (date, datetime)):
            payload[key] = value.isoformat()
        else:
            payload[key] = value
    return '/admin?' + urlencode(payload)


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


def schedule(coro_fn):
    """Helper to spawn an async UI handler from a sync event."""
    background_tasks.create(coro_fn())
