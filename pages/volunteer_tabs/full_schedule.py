"""Volunteer Full Schedule tab: every role's shifts for one day, read-only."""

import math
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from nicegui import app, ui

from application.services import SystemConfigService, get_user_from_discord_id
from application.services.volunteer import DayGrid, GridShift, VolunteerScheduleService
from application.utils.tenant_session import tenant_session_get, tenant_session_set
from application.utils.timezone import format_local_time, timezone_label, today_local
from theme.dialog._helpers import form_dialog
from theme.empty_state import empty_panel
from theme.help import help_icon
from theme.notify import notify_error
from theme.page_header import page_header
from theme.timer_teardown import PageTimer

_DAY_KEY = 'volunteer:schedule_day'
# One grid hour, in px. Mirrored by --wiz-vgrid-hour in styles.css; the page
# needs it to work out how many names fit in a block.
HOUR_PX = 48
_LINE_PX = 18
_BLOCK_CHROME_PX = 32


def event_days(start: date, end: date) -> List[date]:
    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


def opening_day(days: List[date], stored: Optional[str], today: date) -> Optional[date]:
    """Remembered day, else today during the event, else its first day."""
    if not days:
        return None
    by_iso = {d.isoformat(): d for d in days}
    if stored in by_iso:
        return by_iso[stored]
    return today if today in days else days[0]


def day_label(d: date) -> str:
    return f"{d.strftime('%a')} {d.day}"


def names_that_fit(shift: GridShift) -> int:
    """How many names a block shows before "+N more" takes the last line."""
    height = (shift.end_hour - shift.start_hour) * HOUR_PX
    lines = max(1, math.floor((height - _BLOCK_CHROME_PX) / _LINE_PX))
    if len(shift.people) <= lines:
        return len(shift.people)
    return max(0, lines - 1)


def person_label(name: str, is_viewer: bool) -> str:
    return f'{name} (you)' if is_viewer else name


def _range(shift: GridShift) -> str:
    return f'{format_local_time(shift.starts_at)}–{format_local_time(shift.ends_at)}'


def _px(hours: float) -> str:
    return f'{hours * HOUR_PX:.1f}px'


async def full_schedule_tab() -> None:
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    service = VolunteerScheduleService()
    start, end = await SystemConfigService.get_event_window()
    days = event_days(start, end)
    state = {'day': opening_day(days, tenant_session_get(_DAY_KEY), today_local())}

    def open_names(shift: GridShift, position: str) -> None:
        with form_dialog(position, card_classes='dialog-card dialog-card--sm') as dialog:
            with ui.column().classes('q-pa-md gap-1 full-width'):
                ui.label(_range(shift)).classes('text-caption')
                for person in shift.people:
                    ui.label(person_label(person.name, person.is_viewer)) \
                        .classes('text-weight-bold' if person.is_viewer else '')
        dialog.open()

    def render_shift(shift: GridShift, position: str, grid: DayGrid) -> None:
        classes = 'wiz-vgrid__shift'
        if shift.has_viewer:
            classes += ' wiz-vgrid__shift--mine'
        top = shift.start_hour - grid.first_hour
        with ui.element('div').classes(classes).style(
            # 3px in from each hour line so back-to-back shifts never touch.
            f'top: calc({_px(top)} + 3px); height: calc({_px(shift.end_hour - shift.start_hour)} - 6px); '
            f'left: calc(4px + (100% - 8px) * {shift.lane} / {shift.lanes}); '
            f'width: calc((100% - 8px) / {shift.lanes} - {4 if shift.lanes > 1 else 0}px);'
        ):
            ui.label(_range(shift)).classes('wiz-vgrid__time')
            shown = names_that_fit(shift)
            for person in shift.people[:shown]:
                ui.label(person_label(person.name, person.is_viewer)).classes(
                    'wiz-vgrid__name' + (' wiz-vgrid__name--you' if person.is_viewer else '')
                )
            hidden = len(shift.people) - shown
            if hidden:
                ui.button(f'+{hidden} more', on_click=lambda s=shift, p=position: open_names(s, p)) \
                    .props('flat dense no-caps size=sm color=primary').classes('wiz-vgrid__more')
            elif not shift.people:
                ui.label('Nobody yet').classes('wiz-vgrid__open')

    def render_now(grid: DayGrid, now_hour: Optional[float]) -> None:
        if now_hour is not None:
            ui.element('div').classes('wiz-vgrid__now').style(f'top: {_px(now_hour - grid.first_hour)};')

    @ui.refreshable
    def day_bar() -> None:
        with ui.row().classes('wiz-vgrid-days items-center'):
            for d in days:
                selected = d == state['day']
                button = ui.button(day_label(d), on_click=lambda d=d: pick_day(d)) \
                    .props(f"no-caps rounded {'unelevated color=primary' if selected else 'outline'}") \
                    .classes('wiz-vgrid-day')
                button.props(f'aria-pressed={"true" if selected else "false"}')

    @ui.refreshable
    async def grid_view() -> None:
        if state['day'] is None:
            empty_panel('No event dates are set yet.', icon='event_busy')
            return
        try:
            grid = await service.day_grid(user, state['day'])
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        if not grid.columns:
            empty_panel(f"No shifts on {day_label(state['day'])}.", icon='event_busy')
            return
        now_hour = grid.hour_at(datetime.now(timezone.utc))
        with ui.row().classes('wiz-vgrid-legend items-center'):
            with ui.row().classes('items-center gap-1 no-wrap'):
                ui.element('span').classes('wiz-vgrid-legend__mine')
                ui.label('Your shifts')
            if now_hour is not None:
                with ui.row().classes('items-center gap-1 no-wrap'):
                    ui.element('span').classes('wiz-vgrid-legend__now')
                    ui.label('Now')
            if len(grid.columns) > 2:
                ui.label('Swipe sideways for more roles').classes('lt-md wiz-vgrid-legend__hint')
        body_height = _px(grid.last_hour - grid.first_hour)
        region = ui.element('div').classes('wiz-vgrid').props(
            f'tabindex=0 role=region aria-label="Volunteer schedule for {day_label(state["day"])}"'
        )
        with region:
            with ui.element('div').classes('wiz-vgrid__times'):
                ui.element('div').classes('wiz-vgrid__head')
                with ui.element('div').classes('wiz-vgrid__body').style(f'height: {body_height};'):
                    for hour in grid.hours:
                        ui.label(format_local_time(grid.midnight + timedelta(hours=hour))) \
                            .classes('wiz-vgrid__hour').style(f'top: {_px(hour - grid.first_hour)};')
                    render_now(grid, now_hour)
            for column in grid.columns:
                with ui.element('div').classes('wiz-vgrid__col'):
                    ui.label(column.position).classes('wiz-vgrid__head')
                    with ui.element('div').classes('wiz-vgrid__body wiz-vgrid__body--lines') \
                            .style(f'height: {body_height};'):
                        for shift in column.shifts:
                            render_shift(shift, column.position, grid)
                        render_now(grid, now_hour)

    def pick_day(d: date) -> None:
        state['day'] = d
        tenant_session_set(_DAY_KEY, d.isoformat())
        day_bar.refresh()
        grid_view.refresh()

    with ui.column().classes('page-container-wide'):
        with page_header(
            'Volunteer schedule',
            f"Who's at which station, hour by hour. Times are {timezone_label()}.",
        ):
            await help_icon(('full-schedule', 'The full schedule'), user=user)
        day_bar()
        await grid_view()
    # Keeps the Now line and any schedule changes current on a screen left open
    # at a desk.
    PageTimer(300, grid_view.refresh)
