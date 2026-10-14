"""Volunteer Full Schedule tab: every role's shifts for one day, read-only."""

import math
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

from nicegui import app, ui

from application.services import (
    SystemConfigService,
    TablePreferenceService,
    get_user_from_discord_id,
)
from application.services.volunteer import (
    DayGrid,
    GridRole,
    GridShift,
    VolunteerScheduleService,
    apply_roles,
    arrange_roles,
    roles_config,
)
from application.utils.tenant_session import tenant_session_get, tenant_session_set
from application.utils.timezone import format_local_time, timezone_label, today_local
from theme.dialog._helpers import dialog_actions, dialog_more_menu, form_dialog
from theme.empty_state import empty_panel
from theme.help import help_icon
from theme.menu import menu_action
from theme.notify import notify_error
from theme.page_header import page_header
from theme.tables.preferences import TableKeys
from theme.timer_teardown import PageTimer

_DAY_KEY = 'volunteer:schedule_day'
# One grid hour, in px. Mirrored by --wiz-vgrid-hour in styles.css; the page
# needs it to work out how many names fit in a block.
HOUR_PX = 48
_LINE_PX = 18
_BLOCK_CHROME_PX = 32


@dataclass
class _ViewState:
    day: Optional[date]
    roles: Tuple[GridRole, ...]
    saved: list


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


def is_customized(roles, positions) -> bool:
    """Whether the viewer's columns differ from everyone's default."""
    return any(not r.visible for r in roles) \
        or [r.position_id for r in roles] != [pid for pid, _ in positions]


async def full_schedule_tab() -> None:
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    service = VolunteerScheduleService()
    start, end = await SystemConfigService.get_event_window()
    days = event_days(start, end)
    prefs = TablePreferenceService()
    try:
        positions = await service.grid_roles(user)
    except (ValueError, PermissionError):
        positions = []
    stored = await prefs.get(user, TableKeys.VOLUNTEER_FULL_SCHEDULE) if user else None
    saved = (stored or {}).get('columns') or []
    state = _ViewState(
        day=opening_day(days, tenant_session_get(_DAY_KEY), today_local()),
        roles=arrange_roles(positions, saved),
        saved=saved,
    )

    def open_names(shift: GridShift, position: str) -> None:
        with form_dialog(position, card_classes='dialog-card dialog-card--sm') as dialog:
            with ui.column().classes('q-pa-md gap-1 full-width'):
                ui.label(_range(shift)).classes('text-caption')
                for person in shift.people:
                    ui.label(person_label(person.name, person.is_viewer)) \
                        .classes('text-weight-bold' if person.is_viewer else '')
        dialog.open()

    def open_columns() -> None:
        staged = list(state.roles)
        dragging = {'index': -1}

        with form_dialog('Columns', card_classes='dialog-card dialog-card--sm') as dialog:
            with ui.column().classes('q-pa-md gap-2 full-width'):
                ui.label('Pick which roles you see and their order. Saved for you on every device.') \
                    .classes('text-caption text-muted')
                role_list = ui.column().classes('full-width gap-0')

            def move(index: int, delta: int) -> None:
                target = index + delta
                if 0 <= target < len(staged):
                    staged[index], staged[target] = staged[target], staged[index]
                    render_roles()

            def drop(source: int, target: int) -> None:
                if source == target or not 0 <= source < len(staged):
                    return
                staged.insert(min(target, len(staged) - 1), staged.pop(source))
                render_roles()

            def render_roles() -> None:
                role_list.clear()
                with role_list:
                    for index, entry in enumerate(staged):
                        # Drag adds to the ▲/▼ buttons rather than replacing
                        # them: touch screens and keyboards can't drag.
                        row = ui.row().classes('full-width items-center no-wrap gap-2 q-py-xs')
                        row.props('draggable="true"')
                        row.on('dragstart', lambda _, i=index: dragging.update(index=i))
                        row.on('dragover.prevent', lambda: None)
                        row.on('drop', lambda _, i=index: drop(dragging['index'], i))
                        with row:
                            ui.icon('drag_indicator').classes('text-muted cursor-move gt-sm') \
                                .tooltip('Drag to reorder')
                            ui.checkbox(
                                entry.name, value=entry.visible,
                                on_change=lambda e, i=index: set_visible(i, e.value),
                            ).props('dense').classes('col-grow')
                            up = ui.button(icon='arrow_upward', on_click=lambda _, i=index: move(i, -1)) \
                                .props('flat dense round aria-label="Move up"').tooltip('Move up')
                            up.set_enabled(index > 0)
                            down = ui.button(icon='arrow_downward', on_click=lambda _, i=index: move(i, 1)) \
                                .props('flat dense round aria-label="Move down"').tooltip('Move down')
                            down.set_enabled(index < len(staged) - 1)

            def set_visible(index: int, visible: bool) -> None:
                staged[index] = replace(staged[index], visible=bool(visible))

            def show_all() -> None:
                staged[:] = arrange_roles(positions, None)
                render_roles()

            async def save() -> None:
                if not any(r.visible for r in staged):
                    ui.notify('Keep at least one role showing.', color='warning')
                    return
                if user is None:
                    return
                roles = tuple(staged)
                config = {'columns': roles_config(roles, state.saved, TablePreferenceService.MAX_COLUMNS)}
                try:
                    stored = await prefs.save(user, TableKeys.VOLUNTEER_FULL_SCHEDULE, config)
                except ValueError as e:
                    ui.notify(str(e), color='warning')
                    return
                state.saved = stored.get('columns', [])
                state.roles = roles
                dialog.close()
                day_bar.refresh()
                grid_view.refresh()

            render_roles()
            with dialog_actions():
                with dialog_more_menu():
                    menu_action('restart_alt', 'Show all in default order', show_all)
                ui.space()
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save', on_click=save).props('color=primary')
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
                selected = d == state.day
                button = ui.button(day_label(d), on_click=lambda d=d: pick_day(d)) \
                    .props(f"no-caps rounded {'unelevated color=primary' if selected else 'outline'}") \
                    .classes('wiz-vgrid-day')
                button.props(f'aria-pressed={"true" if selected else "false"}')
            if positions:
                ui.space()
                customized = is_customized(state.roles, positions)
                with ui.button('Columns', icon='view_column', on_click=open_columns) \
                        .props('no-caps outline rounded').classes('wiz-vgrid-columns'):
                    if customized:
                        ui.badge().props('floating rounded color=primary').classes('wiz-vgrid-columns__dot')
                        ui.label('(customized)').classes('wiz-sr-only')

    @ui.refreshable
    async def grid_view() -> None:
        if state.day is None:
            empty_panel('No event dates are set yet.', icon='event_busy')
            return
        try:
            everyone = await service.day_grid(user, state.day)
        except (ValueError, PermissionError) as e:
            notify_error(e)
            return
        if not everyone.columns:
            empty_panel(f"No shifts on {day_label(state.day)}.", icon='event_busy')
            return
        grid = apply_roles(everyone, state.roles)
        if not grid.columns:
            empty_panel(
                f"Every role with shifts on {day_label(state.day)} is hidden. "
                'Use Columns to show them.',
                icon='visibility_off',
            )
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
            f'tabindex=0 role=region aria-label="Volunteer schedule for {day_label(state.day)}"'
        )
        # The Volunteer tabs are swipeable, so a sideways swipe meant to scroll
        # the grid would flip to the next tab. Keep the gesture inside the grid.
        for gesture in ('touchstart', 'mousedown'):
            region.on(gesture, js_handler='(e) => e.stopPropagation()')
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
        state.day = d
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
