"""Audit Log Viewer report.

Server-side paginated, filterable view of the AuditLog table.
"""

from typing import Optional

from nicegui import ui

from application.services import AuditService
from application.utils.timezone import format_eastern_display
from .shared import (
    date_range_filter,
    default_date_range,
    eastern_bounds,
    navigate_with_params,
    paginated_event_log,
    parse_details,
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
                        action=(action_input.value or '').strip() or None,
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

        rows = []
        for log in logs:
            _, display = parse_details(log.details)
            truncated = display[:200] + ('…' if len(display) > 200 else '')
            rows.append({
                'log_id': log.id,
                'created_at': format_eastern_display(log.created_at),
                'user_id': log.user_id,
                'user': log.user.preferred_name if log.user else f'User {log.user_id}',
                'action': log.action,
                'details': truncated,
                'full_details': display,
            })
        columns = [
            {'name': 'created_at', 'label': 'When (ET)', 'field': 'created_at', 'sortable': False},
            {'name': 'user', 'label': 'User', 'field': 'user', 'sortable': False},
            {'name': 'action', 'label': 'Action', 'field': 'action', 'sortable': False},
            {'name': 'details', 'label': 'Details', 'field': 'details', 'sortable': False},
        ]

        def _on_user_click(row: dict) -> None:
            clicked_uid = row.get('user_id')
            if clicked_uid:
                navigate_with_params(
                    report='audit',
                    start=start_d, end=end_d,
                    user_id=clicked_uid,
                    action=action_filter or None,
                )

        def _go_to_page(new_page: int) -> None:
            navigate_with_params(
                report='audit',
                start=start_d, end=end_d,
                user_id=user_id_int,
                action=action_filter or None,
                page=new_page,
            )

        paginated_event_log(
            columns=columns,
            rows=rows,
            row_key='log_id',
            total=total,
            page=page_int,
            page_size=PAGE_SIZE,
            on_page=_go_to_page,
            csv_filename_prefix=f'audit-log-page-{page_int}-{start_d}-to-{end_d}',
            count_label=f'{total} entries',
            note=(
                'Click a row to filter by that user. Click the details cell to expand JSON. '
                'Try action filters like "match." or "user.role_".'
            ),
            on_row_click=_on_user_click,
        )
