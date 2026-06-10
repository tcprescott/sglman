"""Volunteer Coverage report.

Per-shift filled/needed counts across a date range, highlighting understaffed
shifts.
"""

from typing import Optional

from nicegui import ui

from application.services.volunteer_schedule_service import VolunteerScheduleService
from application.utils.timezone import format_eastern_display
from .shared import (
    csv_export_button,
    date_range_filter,
    default_date_range,
    eastern_bounds,
    navigate_with_params,
    report_page_shell,
)


async def volunteers_page(
    start: Optional[str] = None,
    end: Optional[str] = None,
    **_unused,
) -> None:
    start_d, end_d = await default_date_range(start, end)

    with report_page_shell('Volunteer Coverage'):
        with ui.card().classes('full-width q-pa-md'):
            date_range_filter(
                start_d,
                end_d,
                on_change=lambda s, e: navigate_with_params(report='volunteers', start=s, end=e),
            )

        bounds_start, bounds_end = eastern_bounds(start_d, end_d)
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

        rows = [
            {
                'position': r['position'],
                'label': r['label'],
                'starts_at': format_eastern_display(r['starts_at']),
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
            ui.table(columns=columns, rows=rows, pagination=25, row_key='starts_at') \
                .classes('full-width')
