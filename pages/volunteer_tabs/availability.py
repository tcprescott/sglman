"""Volunteer My Availability tab."""

from datetime import timedelta
from types import SimpleNamespace

from nicegui import ui

from application.services import current_user_from_storage, SystemConfigService
from application.services.volunteer_availability_service import VolunteerAvailabilityService
from application.utils.timezone import (
    format_eastern_date,
    format_eastern_time,
    parse_eastern_datetime,
    to_eastern,
)
from models import VolunteerAvailabilityStatus


_STATUS_OPTIONS = {
    VolunteerAvailabilityStatus.PREFERRED.value: 'Preferred',
    VolunteerAvailabilityStatus.AVAILABLE.value: 'Available',
    VolunteerAvailabilityStatus.UNAVAILABLE.value: 'Unavailable',
}

# Colors for the effective-availability graph, keyed by resolved status.
_STATUS_COLORS = {
    VolunteerAvailabilityStatus.UNAVAILABLE: '#d32f2f',
    VolunteerAvailabilityStatus.PREFERRED: '#2e7d32',
    VolunteerAvailabilityStatus.AVAILABLE: '#90caf9',
}
_NONE_COLOR = '#eeeeee'


def _status_label(status) -> str:
    if status is None:
        return 'No availability'
    return _STATUS_OPTIONS.get(status.value, str(status))


async def availability_tab() -> None:
    user = await current_user_from_storage()
    if user is None:
        ui.label('You must be logged in.').classes('text-error')
        return

    service = VolunteerAvailabilityService()

    event_start, event_end = await SystemConfigService.get_event_window()
    existing = await service.availability_for(user)

    # Calendar days spanned by the event window (US/Eastern), as
    # (date, day_start_utc, day_end_utc) tuples for the graph.
    event_days: list[tuple] = []
    cursor = event_start
    last_day = event_end
    while cursor <= last_day:
        next_day = cursor + timedelta(days=1)
        event_days.append((
            cursor,
            parse_eastern_datetime(cursor.isoformat(), '00:00'),
            parse_eastern_datetime(next_day.isoformat(), '00:00'),
        ))
        cursor = next_day

    # Working set of rows; each is a mutable dict the inputs bind to.
    rows: list[dict] = [
        {
            'date': format_eastern_date(w.starts_at),
            'start': format_eastern_time(w.starts_at),
            'end': format_eastern_time(to_eastern(w.ends_at)),
            'status': w.status.value if hasattr(w.status, 'value') else str(w.status),
        }
        for w in existing
    ]

    with ui.column().classes('page-container'):
        with ui.row().classes('header-row'):
            ui.label('My Availability').classes('page-title')
        ui.separator().classes('separator-spacing')
        ui.label(
            f'Event window: {format_eastern_date(event_start)} → {format_eastern_date(event_end)} '
            '(US/Eastern). Add the windows you can work.'
        ).classes('italic-note')

        @ui.refreshable
        def window_rows() -> None:
            if not rows:
                ui.label('No availability windows yet. Add one below.').classes('italic-note')
            for row in rows:
                with ui.row().classes('items-center gap-2 q-mb-xs'):
                    ui.input('Date', value=row['date']) \
                        .props('type=date dense').bind_value(row, 'date') \
                        .on_value_change(effective_graph.refresh)
                    ui.input('Start', value=row['start']) \
                        .props('type=time dense').bind_value(row, 'start') \
                        .on_value_change(effective_graph.refresh)
                    ui.input('End', value=row['end']) \
                        .props('type=time dense').bind_value(row, 'end') \
                        .on_value_change(effective_graph.refresh)
                    ui.select(_STATUS_OPTIONS, value=row['status']) \
                        .props('dense').bind_value(row, 'status').classes('w-40') \
                        .on_value_change(effective_graph.refresh)
                    ui.button(icon='delete', on_click=lambda r=row: _remove(r)) \
                        .props('flat dense color=negative')

        def _windows_from_rows() -> list:
            """Parse the working rows into window-like objects, skipping any
            that are incomplete or invalid (so the graph stays live as you edit)."""
            parsed = []
            for row in rows:
                if not row['date'] or not row['start'] or not row['end']:
                    continue
                try:
                    starts_at = parse_eastern_datetime(row['date'], row['start'])
                    ends_at = parse_eastern_datetime(row['date'], row['end'])
                    status = VolunteerAvailabilityStatus(row['status'])
                except (ValueError, KeyError):
                    continue
                if ends_at <= starts_at:
                    continue
                parsed.append(SimpleNamespace(starts_at=starts_at, ends_at=ends_at, status=status))
            return parsed

        @ui.refreshable
        def effective_graph() -> None:
            windows = _windows_from_rows()
            with ui.column().classes('w-full gap-1 q-mt-md'):
                ui.label('Effective availability').classes('text-subtitle2')
                ui.label('Where windows overlap, Unavailable beats Preferred beats Available.') \
                    .classes('italic-note')
                with ui.row().classes('items-center gap-4 q-mb-xs'):
                    for legend_status in (
                        VolunteerAvailabilityStatus.UNAVAILABLE,
                        VolunteerAvailabilityStatus.PREFERRED,
                        VolunteerAvailabilityStatus.AVAILABLE,
                        None,
                    ):
                        with ui.row().classes('items-center gap-1 no-wrap'):
                            ui.element('div').style(
                                'width:14px;height:14px;border-radius:3px;border:1px solid #bbb;'
                                f'background:{_STATUS_COLORS.get(legend_status, _NONE_COLOR)}'
                            )
                            ui.label(_status_label(legend_status)).classes('text-caption')
                for day, day_start, day_end in event_days:
                    segments = service.effective_segments(windows, day_start, day_end)
                    total = (day_end - day_start).total_seconds()
                    with ui.row().classes('items-center no-wrap gap-2 w-full'):
                        ui.label(day.strftime('%a %b %d')).classes('text-caption').style('width:96px;flex:none')
                        with ui.element('div').classes('flex-grow').style(
                            'display:flex;height:18px;border-radius:4px;overflow:hidden;border:1px solid #bbb'
                        ):
                            if not segments:
                                ui.element('div').style(f'width:100%;background:{_NONE_COLOR}')
                            for seg_start, seg_end, status in segments:
                                pct = (seg_end - seg_start).total_seconds() / total * 100
                                seg = ui.element('div').style(
                                    f'width:{pct}%;background:{_STATUS_COLORS.get(status, _NONE_COLOR)}'
                                )
                                seg.tooltip(
                                    f'{format_eastern_time(seg_start)}–{format_eastern_time(seg_end)} · '
                                    f'{_status_label(status)}'
                                )
                with ui.row().classes('items-center no-wrap gap-2 w-full'):
                    ui.label('').style('width:96px;flex:none')
                    with ui.row().classes('flex-grow justify-between'):
                        for tick in ('00:00', '06:00', '12:00', '18:00', '24:00'):
                            ui.label(tick).classes('text-caption text-grey')

        def _remove(row: dict) -> None:
            rows.remove(row)
            window_rows.refresh()
            effective_graph.refresh()

        def _add() -> None:
            rows.append({
                'date': format_eastern_date(event_start),
                'start': '09:00',
                'end': '13:00',
                'status': VolunteerAvailabilityStatus.AVAILABLE.value,
            })
            window_rows.refresh()
            effective_graph.refresh()

        window_rows()
        effective_graph()

        async def save() -> None:
            windows = []
            try:
                for row in rows:
                    if not row['date'] or not row['start'] or not row['end']:
                        raise ValueError('Every window needs a date, start, and end.')
                    starts_at = parse_eastern_datetime(row['date'], row['start'])
                    ends_at = parse_eastern_datetime(row['date'], row['end'])
                    if ends_at <= starts_at:
                        raise ValueError('Each availability window must end after it starts.')
                    status = VolunteerAvailabilityStatus(row['status'])
                    windows.append((starts_at, ends_at, status, None))
                await service.set_windows(user, windows)
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Availability saved.', color='positive')

        with ui.row().classes('q-mt-md gap-2'):
            ui.button('Add window', icon='add', on_click=_add).props('flat color=primary')
            ui.button('Save availability', icon='save', on_click=save).props('color=primary')
