"""Audit Log Viewer report.

Server-side paginated, filterable view of the AuditLog table.
"""

from typing import Optional

from nicegui import ui

from application.services import AuditService
from application.utils.timezone import format_eastern_display
from .shared import (
    csv_export_button,
    date_range_filter,
    default_date_range,
    eastern_bounds,
    navigate_with_params,
    parse_int,
    report_page_shell,
)


PAGE_SIZE = 50


async def audit_page(
    start: Optional[str] = None,
    end: Optional[str] = None,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    page: Optional[int] = None,
    **_unused,
) -> None:
    start_d, end_d = await default_date_range(start, end)
    user_id_int = parse_int(user_id)
    page_int = max(1, parse_int(page) or 1)
    action_filter = (action or '').strip()

    with report_page_shell('Audit Log'):
        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center gap-3'):
                date_range_filter(
                    start_d, end_d,
                    on_change=lambda s, e: navigate_with_params(
                        report='audit',
                        start=s, end=e,
                        user_id=user_id_int,
                        action=action_filter or None,
                    ),
                )
                action_input = ui.input(
                    'Action contains',
                    value=action_filter,
                ).props('dense').classes('control-width')

                def _on_action(_e):
                    navigate_with_params(
                        report='audit',
                        start=start_d, end=end_d,
                        user_id=user_id_int,
                        action=action_input.value or None,
                    )
                action_input.on('blur', _on_action)
                action_input.on('keydown.enter', _on_action)

                if user_id_int is not None:
                    ui.button(
                        'Clear user filter', icon='close',
                        on_click=lambda: navigate_with_params(
                            report='audit',
                            start=start_d, end=end_d,
                            action=action_filter or None,
                        ),
                    ).props('flat dense')

        bounds_start, bounds_end = eastern_bounds(start_d, end_d)
        service = AuditService()
        total = await service.count_logs(
            start=bounds_start, end=bounds_end,
            user_id=user_id_int, action_contains=action_filter or None,
        )
        logs = await service.list_logs(
            start=bounds_start, end=bounds_end,
            user_id=user_id_int, action_contains=action_filter or None,
            limit=PAGE_SIZE, offset=(page_int - 1) * PAGE_SIZE,
        )

        rows = [
            {
                'log_id': log.id,
                'created_at': format_eastern_display(log.created_at),
                'user_id': log.user_id,
                'user': log.user.preferred_name if log.user else f'User {log.user_id}',
                'action': log.action,
                'details': (log.details or '')[:200] + ('…' if log.details and len(log.details) > 200 else ''),
                'full_details': log.details or '',
            }
            for log in logs
        ]
        columns = [
            {'name': 'created_at', 'label': 'When (ET)', 'field': 'created_at', 'sortable': False},
            {'name': 'user', 'label': 'User', 'field': 'user', 'sortable': False},
            {'name': 'action', 'label': 'Action', 'field': 'action', 'sortable': False},
            {'name': 'details', 'label': 'Details', 'field': 'details', 'sortable': False},
        ]

        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center justify-between full-width'):
                ui.label(f'{total} entries').classes('text-h6')
                csv_export_button(
                    f'audit-log-page-{page_int}-{start_d}-to-{end_d}',
                    lambda: columns,
                    lambda: rows,
                )

            def _on_user_click(e):
                row = e.args[1] if isinstance(e.args, list) and len(e.args) > 1 else e.args
                clicked_uid = row.get('user_id') if isinstance(row, dict) else None
                if clicked_uid:
                    navigate_with_params(
                        report='audit',
                        start=start_d, end=end_d,
                        user_id=clicked_uid,
                        action=action_filter or None,
                    )

            table = ui.table(
                columns=columns,
                rows=rows,
                row_key='log_id',
            ).classes('full-width')
            table.on('row-click', _on_user_click)
            ui.label('Click a row to filter by that user. Showing first 200 chars of details.').classes('italic-note')

            # Pager
            total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            with ui.row().classes('items-center q-mt-sm'):
                ui.label(f'Page {page_int} of {total_pages}').classes('text-caption')
                ui.button(
                    'Previous', icon='chevron_left',
                    on_click=lambda: navigate_with_params(
                        report='audit',
                        start=start_d, end=end_d,
                        user_id=user_id_int,
                        action=action_filter or None,
                        page=page_int - 1,
                    ),
                ).props('flat dense').set_enabled(page_int > 1)
                ui.button(
                    'Next', icon='chevron_right',
                    on_click=lambda: navigate_with_params(
                        report='audit',
                        start=start_d, end=end_d,
                        user_id=user_id_int,
                        action=action_filter or None,
                        page=page_int + 1,
                    ),
                ).props('flat dense').set_enabled(page_int < total_pages)
