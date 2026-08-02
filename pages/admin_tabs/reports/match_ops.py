"""Match Operations detail report.

Per-match operational metrics (start delay, duration, confirmation lag)
plus per-tournament aggregates.
"""

from typing import Optional

from nicegui import app, ui

from application.services import AuthService, ReportsService, get_user_from_discord_id
from application.utils.timezone import format_local_display
from pages.admin_tabs.links import SCHEDULE, admin_url
from theme.tables.mobile_grid import enable_mobile_grid
from theme.tables.preferences import TableKeys

from .shared import (
    csv_export_button,
    date_range_filter,
    default_date_range,
    display_bounds,
    enable_drill_link,
    navigate_with_params,
    report_page_shell,
    reports_url,
    tournament_filter,
)

STATE_OPTIONS = ['All', 'Scheduled', 'Checked In', 'In Progress', 'Finished']


async def match_ops_page(
    start: Optional[str] = None,
    end: Optional[str] = None,
    tournament_id: Optional[int] = None,
    state: Optional[str] = None,
    **_unused,
) -> None:
    start_d, end_d = await default_date_range(start, end)
    selected_state = state if state in STATE_OPTIONS else 'All'
    viewer = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    can_open_board = await AuthService.can_view_schedule_board(viewer)

    with report_page_shell('Match Operations'):
        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center gap-3'):
                date_range_filter(
                    start_d, end_d,
                    on_change=lambda s, e: navigate_with_params(
                        report='match_ops',
                        start=s, end=e,
                        tournament_id=tournament_id,
                        state=None if selected_state == 'All' else selected_state,
                    ),
                )
                await tournament_filter(
                    tournament_id,
                    on_change=lambda t_id: navigate_with_params(
                        report='match_ops',
                        start=start_d, end=end_d,
                        tournament_id=t_id,
                        state=None if selected_state == 'All' else selected_state,
                    ),
                )
                state_select = ui.select(
                    STATE_OPTIONS,
                    value=selected_state,
                    label='State',
                ).props('dense').classes('control-width')

                def _on_state(_e):
                    navigate_with_params(
                        report='match_ops',
                        start=start_d, end=end_d,
                        tournament_id=tournament_id,
                        state=None if state_select.value == 'All' else state_select.value,
                    )
                state_select.on('update:model-value', _on_state)

        bounds_start, bounds_end = display_bounds(start_d, end_d)
        ops = await ReportsService().match_operations(
            bounds_start, bounds_end, tournament_id=tournament_id,
        )
        rows = ops['rows']
        if selected_state != 'All':
            rows = [r for r in rows if r['state'] == selected_state]

        with ui.card().classes('full-width q-pa-md'):
            ui.label('Per-tournament aggregates').classes('text-h6')
            if not ops['aggregates']:
                ui.label('No matches in window.').classes('italic-note')
            else:
                agg_columns = [
                    {'name': 'tournament_name', 'label': 'Tournament', 'field': 'tournament_name', 'sortable': True},
                    {'name': 'matches_total', 'label': 'Matches', 'field': 'matches_total', 'sortable': True},
                    {'name': 'matches_started', 'label': 'Started', 'field': 'matches_started', 'sortable': True},
                    {'name': 'matches_finished', 'label': 'Finished', 'field': 'matches_finished', 'sortable': True},
                    {'name': 'avg_start_delay_min', 'label': 'Avg start delay (min)', 'field': 'avg_start_delay_min', 'sortable': True},
                    {'name': 'avg_duration_min', 'label': 'Avg duration (min)', 'field': 'avg_duration_min', 'sortable': True},
                    {'name': 'expected_avg_min', 'label': 'Expected (min)', 'field': 'expected_avg_min', 'sortable': True},
                    {'name': 'on_time_pct', 'label': 'On-time %', 'field': 'on_time_pct', 'sortable': True},
                ]
                agg_table = ui.table(
                    columns=agg_columns,
                    rows=ops['aggregates'],
                    row_key='tournament_id',
                ).classes('full-width')
                # The board takes no tournament param, so this aggregate drills
                # *within* reports — re-filtering this report to the tournament
                # whose number the operator just read.
                agg_actions = enable_drill_link(
                    agg_table, agg_columns, ops['aggregates'],
                    lambda r: reports_url(
                        'match_ops',
                        start=start_d, end=end_d,
                        tournament_id=r['tournament_id'],
                        state=None if selected_state == 'All' else selected_state,
                    ),
                    hint='Show only this tournament',
                )
                enable_mobile_grid(agg_table, agg_columns, actions=agg_actions,
                                   table_key=TableKeys.REPORTS_MATCH_OPS_SUMMARY)

        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center justify-between full-width'):
                ui.label('Matches').classes('text-h6')
                detail_rows = [
                    {
                        **r,
                        'scheduled_at': format_local_display(r['scheduled_at']),
                    }
                    for r in rows
                ]
                detail_columns = [
                    {'name': 'match_id', 'label': 'Match', 'field': 'match_id', 'sortable': True},
                    {'name': 'tournament_name', 'label': 'Tournament', 'field': 'tournament_name', 'sortable': True},
                    {'name': 'scheduled_at', 'label': 'Scheduled', 'field': 'scheduled_at', 'sortable': True},
                    {'name': 'state', 'label': 'State', 'field': 'state', 'sortable': True},
                    {'name': 'start_delay_min', 'label': 'Start delay (min)', 'field': 'start_delay_min', 'sortable': True},
                    {'name': 'duration_min', 'label': 'Duration (min)', 'field': 'duration_min', 'sortable': True},
                    {'name': 'confirmation_lag_min', 'label': 'Confirm lag (min)', 'field': 'confirmation_lag_min', 'sortable': True},
                    {'name': 'stage', 'label': 'Stage', 'field': 'stage', 'sortable': True},
                    {'name': 'player_count', 'label': 'Players', 'field': 'player_count', 'sortable': True},
                ]
                csv_export_button(
                    f'match-ops-{start_d}-to-{end_d}',
                    lambda: detail_columns,
                    lambda: detail_rows,
                )
            detail_table = ui.table(
                columns=detail_columns,
                rows=detail_rows,
                pagination=25,
                row_key='match_id',
            ).classes('full-width')
            # A Finished match with no result is found here and confirmed on the
            # board, whose review queue is already built for exactly that pile.
            detail_actions = enable_drill_link(
                detail_table, detail_columns, detail_rows,
                lambda r: admin_url(SCHEDULE, match_id=r['match_id']),
                enabled=can_open_board,
                hint='Open on the schedule board',
            )
            enable_mobile_grid(detail_table, detail_columns, actions=detail_actions,
                               table_key=TableKeys.REPORTS_MATCH_OPS_DETAIL)
