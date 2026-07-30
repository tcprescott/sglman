"""Volunteer Coverage report.

Per-shift filled/needed counts across a date range, highlighting understaffed
shifts.
"""

from typing import Optional

from nicegui import app, ui

from application.services import AuthService, get_user_from_discord_id
from application.services.volunteer.volunteer_schedule_service import VolunteerScheduleService
from application.utils.timezone import format_local_display, to_local
from pages.admin_tabs.links import VOL_SCHEDULE, admin_url
from theme.tables.mobile_grid import enable_mobile_grid
from .shared import (
    csv_export_button,
    date_range_filter,
    default_date_range,
    display_bounds,
    enable_drill_link,
    navigate_with_params,
    report_page_shell,
)


async def volunteers_page(
    start: Optional[str] = None,
    end: Optional[str] = None,
    **_unused,
) -> None:
    start_d, end_d = await default_date_range(start, end)
    # Reading these numbers and staffing the shifts are different capabilities:
    # a crew coordinator can see the coverage report and cannot manage
    # volunteers, so they get the numbers and no link.
    viewer = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    can_staff_shifts = await AuthService.can_manage_volunteers(viewer)

    with report_page_shell('Volunteer Coverage'):
        with ui.card().classes('full-width q-pa-md'):
            date_range_filter(
                start_d,
                end_d,
                on_change=lambda s, e: navigate_with_params(report='volunteers', start=s, end=e),
            )

        bounds_start, bounds_end = display_bounds(start_d, end_d)
        coverage = await VolunteerScheduleService().coverage(bounds_start, bounds_end)

        understaffed = [r for r in coverage if r['understaffed']]
        total_open = sum(r['needed'] - r['filled'] for r in understaffed)

        with ui.card().classes('full-width q-pa-md q-mb-md'):
            ui.label('Understaffed shifts').classes('text-h6')
            if not understaffed:
                ui.label('Every shift in this window is fully staffed. 🎉').classes('italic-note')
            else:
                ui.label(f'{len(understaffed)} shift(s) need {total_open} more volunteer(s).') \
                    .classes('text-body2')
                if can_staff_shifts:
                    # The headline sentence is the most actionable line in the
                    # whole reports section; make it, not only the table, a route.
                    first_day = _eastern_day(min(r['starts_at'] for r in understaffed))
                    ui.button(
                        f'Staff {first_day}', icon='open_in_new',
                        on_click=lambda: ui.navigate.to(
                            admin_url(VOL_SCHEDULE, day=first_day)
                        ),
                    ).props('flat dense color=primary')

        rows = [
            {
                'position': r['position'],
                'label': r['label'],
                'starts_at': format_local_display(r['starts_at']),
                'day': _eastern_day(r['starts_at']),
                'understaffed': r['understaffed'],
                'coverage': f"{r['filled']}/{r['needed']}",
                'status': 'Understaffed' if r['understaffed'] else 'OK',
            }
            for r in coverage
        ]
        columns = [
            {'name': 'position', 'label': 'Position', 'field': 'position', 'sortable': True},
            {'name': 'label', 'label': 'Shift', 'field': 'label', 'sortable': True},
            {'name': 'starts_at', 'label': 'Start', 'field': 'starts_at', 'sortable': True},
            {'name': 'coverage', 'label': 'Filled / Needed', 'field': 'coverage'},
            {'name': 'status', 'label': 'Status', 'field': 'status', 'sortable': True},
        ]

        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center justify-between'):
                ui.label('All shifts').classes('text-h6')
                csv_export_button(
                    f'volunteer-coverage-{start_d}-to-{end_d}',
                    lambda: columns,
                    lambda: rows,
                )
            table = ui.table(columns=columns, rows=rows, pagination=25, row_key='starts_at') \
                .classes('full-width')
            # Only the rows that name work get a route out of it: a fully
            # staffed shift has nowhere to go.
            drill_actions = enable_drill_link(
                table, columns, rows,
                lambda r: admin_url(VOL_SCHEDULE, day=r['day']) if r['understaffed'] else None,
                enabled=can_staff_shifts,
                hint='Staff this day',
            )
            enable_mobile_grid(table, columns, actions=drill_actions)


def _eastern_day(when) -> str:
    """The Eastern calendar day a shift starts on, as the Vol. Schedule names it.

    Never a naive ``.date()``: the stored value is UTC, and a 20:00 ET shift
    lands on the next UTC day.
    """
    return to_local(when).date().isoformat()
