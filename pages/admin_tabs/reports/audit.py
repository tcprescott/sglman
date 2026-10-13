"""Audit Log Viewer report.

Server-side paginated, filterable view of the AuditLog table.
"""

from typing import Any, Optional

from nicegui import app, ui

from application.services import AuditService, AuthService, get_user_from_discord_id
from application.utils.timezone import format_local_display, timezone_label
from theme.tables.preferences import TableKeys

from .shared import (
    date_range_filter,
    default_date_range,
    display_bounds,
    event_jump_options,
    filter_field,
    is_custom_range,
    navigate_with_params,
    paginated_event_log,
    parse_details,
    parse_int,
    report_filter_bar,
    report_jumps,
    report_page_shell,
)

SUBTITLE = 'Who changed what, and when.'


PAGE_SIZE = 50


async def audit_page(
    start: Optional[str] = None,
    end: Optional[str] = None,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    page: Optional[int] = None,
    **_unused,
) -> None:
    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    if actor is None or not await AuthService.is_staff(actor):
        with report_page_shell('Audit Log', SUBTITLE):
            ui.label('Only Staff can view the audit log.').classes('text-error')
        return
    start_d, end_d = await default_date_range(start, end)
    user_id_int = parse_int(user_id)
    page_int = max(1, parse_int(page) or 1)
    action_filter = (action or '').strip()

    def nav(**overrides) -> None:
        params: dict[str, Any] = {
            'report': 'audit',
            'start': start_d, 'end': end_d,
            'user_id': user_id_int,
            'action': action_filter or None,
        }
        params.update(overrides)
        navigate_with_params(**params)

    active = (
        int(await is_custom_range(start_d, end_d)) + int(bool(action_filter))
        + int(user_id_int is not None)
    )
    with report_page_shell('Audit Log', SUBTITLE):
        with report_filter_bar(active):
            date_range_filter(start_d, end_d, on_change=lambda s, e: nav(start=s, end=e))
            action_input = filter_field(ui.input('Action contains', value=action_filter))

            def _on_action(_e):
                nav(action=(action_input.value or '').strip() or None)
            action_input.on('blur', _on_action)
            action_input.on('keydown.enter', _on_action)

            if user_id_int is not None:
                ui.button(
                    'Clear person', icon='close',
                    on_click=lambda: nav(user_id=None),
                ).props('flat dense no-caps color=primary')
            report_jumps(await event_jump_options(), start_d, end_d,
                         on_pick=lambda s, e: nav(start=s, end=e))

        bounds_start, bounds_end = display_bounds(start_d, end_d)
        service = AuditService()
        total = await service.count_logs(
            actor=actor, start=bounds_start, end=bounds_end,
            user_id=user_id_int, action_contains=action_filter or None,
        )
        logs = await service.list_logs(
            actor=actor, start=bounds_start, end=bounds_end,
            user_id=user_id_int, action_contains=action_filter or None,
            limit=PAGE_SIZE, offset=(page_int - 1) * PAGE_SIZE,
        )

        rows = []
        for log in logs:
            _, display = parse_details(log.details)
            truncated = display[:200] + ('…' if len(display) > 200 else '')
            rows.append({
                'log_id': log.id,
                'created_at': format_local_display(log.created_at),
                'user_id': log.user_id,
                'user': log.user.preferred_name if log.user else f'User {log.user_id}',
                'action': log.action,
                'details': truncated,
                'full_details': display,
            })
        columns = [
            {'name': 'created_at', 'label': f'When ({timezone_label()})', 'field': 'created_at', 'sortable': False},
            {'name': 'user', 'label': 'User', 'field': 'user', 'sortable': False},
            {'name': 'action', 'label': 'Action', 'field': 'action', 'sortable': False},
            {'name': 'details', 'label': 'Details', 'field': 'details', 'sortable': False},
        ]

        def _on_user_click(row: dict) -> None:
            clicked_uid = row.get('user_id')
            if clicked_uid:
                nav(user_id=clicked_uid)

        await paginated_event_log(
            title='Entries',
            icon='fact_check',
            columns=columns,
            rows=rows,
            row_key='log_id',
            table_key=TableKeys.REPORTS_AUDIT_LOG,
            total=total,
            page=page_int,
            page_size=PAGE_SIZE,
            on_page=lambda new_page: nav(page=new_page),
            csv_filename_prefix=f'audit-log-page-{page_int}-{start_d}-to-{end_d}',
            count_noun='entries',
            note=(
                'Click a row to filter by that user. Click the details cell to expand JSON. '
                'Try action filters like "match." or "user.role_".'
            ),
            on_row_click=_on_user_click,
        )
