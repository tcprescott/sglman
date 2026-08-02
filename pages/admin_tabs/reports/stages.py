"""Stage Utilization report.

Per-stage scheduled hours, gaps, back-to-back transitions, unplaced
stream-candidate count, plus a stacked-bar timeline.
"""

from typing import Optional

from nicegui import app, ui

from application.services import AuthService, ReportsService, get_user_from_discord_id
from application.utils.timezone import format_local_display
from pages.admin_tabs.links import SCHEDULE, admin_url
from theme.tables.mobile_grid import enable_mobile_grid
from theme.tables.preferences import TableKeys

from .shared import (
    CHART_GOLD,
    CHART_NEUTRAL,
    clicked_row,
    csv_export_button,
    date_range_filter,
    default_date_range,
    display_bounds,
    enable_drill_link,
    navigate_with_params,
    parse_int,
    report_page_shell,
    themed_chart_option,
    tournament_filter,
)


async def stages_page(
    start: Optional[str] = None,
    end: Optional[str] = None,
    tournament_id: Optional[int] = None,
    stage_id: Optional[int] = None,
    **_unused,
) -> None:
    start_d, end_d = await default_date_range(start, end)
    stage_id_int = parse_int(stage_id)
    viewer = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    can_open_board = await AuthService.can_view_schedule_board(viewer)

    with report_page_shell('Stage Utilization'):
        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center gap-3'):
                date_range_filter(
                    start_d, end_d,
                    on_change=lambda s, e: navigate_with_params(
                        report='stages',
                        start=s, end=e,
                        tournament_id=tournament_id,
                        stage_id=stage_id_int,
                    ),
                )
                await tournament_filter(
                    tournament_id,
                    on_change=lambda t_id: navigate_with_params(
                        report='stages',
                        start=start_d, end=end_d,
                        tournament_id=t_id,
                        stage_id=stage_id_int,
                    ),
                )
                if stage_id_int is not None:
                    ui.button(
                        'Clear stage filter', icon='close',
                        on_click=lambda: navigate_with_params(
                            report='stages',
                            start=start_d, end=end_d,
                            tournament_id=tournament_id,
                        ),
                    ).props('flat dense')

        bounds_start, bounds_end = display_bounds(start_d, end_d)
        data = await ReportsService().stage_utilization(
            bounds_start, bounds_end,
            tournament_id=tournament_id,
            stage_id=stage_id_int,
        )
        stages = data['stages']

        with ui.card().classes('chart-container q-pa-md'):
            ui.label('Hours scheduled per stage').classes('text-h6')
            if not stages:
                ui.label('No active stages in the filter.').classes('italic-note')
            else:
                _render_utilization_chart(stages)

        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center justify-between full-width'):
                ui.label(
                    f'Per-stage summary ({data["unplaced_candidate_count"]} '
                    f'unplaced stream candidate{"s" if data["unplaced_candidate_count"] != 1 else ""})'
                ).classes('text-h6')

                summary_rows = [
                    {
                        'stage_id': r['stage_id'],
                        'stage': r['stage_name'],
                        'matches': len(r['matches']),
                        'scheduled_hours': r['scheduled_hours'],
                        'gap_hours': r['gap_hours'],
                        'back_to_back': r['back_to_back_count'],
                    }
                    for r in stages
                ]
                summary_columns = [
                    {'name': 'stage', 'label': 'Stage', 'field': 'stage', 'sortable': True},
                    {'name': 'matches', 'label': 'Matches', 'field': 'matches', 'sortable': True},
                    {'name': 'scheduled_hours', 'label': 'Scheduled hours', 'field': 'scheduled_hours', 'sortable': True},
                    {'name': 'gap_hours', 'label': 'Gap hours', 'field': 'gap_hours', 'sortable': True},
                    {'name': 'back_to_back', 'label': 'Back-to-back <15min', 'field': 'back_to_back', 'sortable': True},
                ]
                csv_export_button(
                    f'stage-utilization-{start_d}-to-{end_d}',
                    lambda: summary_columns,
                    lambda: summary_rows,
                )

            def _row_clicked(e):
                rid = clicked_row(e).get('stage_id')
                if rid:
                    navigate_with_params(
                        report='stages',
                        start=start_d, end=end_d,
                        tournament_id=tournament_id,
                        stage_id=rid,
                    )

            summary_table = ui.table(
                columns=summary_columns,
                rows=summary_rows,
                row_key='stage_id',
            ).classes('full-width wiz-rowclick')
            summary_table.on('row-click', _row_clicked)
            enable_mobile_grid(summary_table, summary_columns, row_click_event='row-click',
                               table_key=TableKeys.REPORTS_STAGE_SUMMARY)
            if stage_id_int is None:
                ui.label('Click a row to filter to a single stage.').classes('italic-note')

        if stage_id_int is not None and stages:
            with ui.card().classes('full-width q-pa-md'):
                ui.label(f'Matches on {stages[0]["stage_name"]}').classes('text-h6')
                match_rows = [
                    {
                        'match_id': m['match_id'],
                        'tournament': m['tournament_name'],
                        'scheduled_at': format_local_display(m['scheduled_at']),
                        'start': format_local_display(m['start']),
                        'end': format_local_display(m['end']),
                    }
                    for m in stages[0]['matches']
                ]
                match_columns = [
                    {'name': 'match_id', 'label': 'Match', 'field': 'match_id', 'sortable': True},
                    {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament', 'sortable': True},
                    {'name': 'scheduled_at', 'label': 'Scheduled', 'field': 'scheduled_at', 'sortable': True},
                    {'name': 'start', 'label': 'Window start', 'field': 'start', 'sortable': True},
                    {'name': 'end', 'label': 'Window end', 'field': 'end', 'sortable': True},
                ]
                match_table = ui.table(
                    columns=match_columns,
                    rows=match_rows,
                    pagination=25,
                    row_key='match_id',
                ).classes('full-width')
                match_actions = enable_drill_link(
                    match_table, match_columns, match_rows,
                    lambda r: admin_url(SCHEDULE, match_id=r['match_id']),
                    enabled=can_open_board,
                    hint='Open on the schedule board',
                )
                enable_mobile_grid(match_table, match_columns, actions=match_actions,
                                   table_key=TableKeys.REPORTS_STAGE_MATCHES)


def _render_utilization_chart(stages) -> None:
    """Horizontal bar of scheduled vs gap hours per stage."""
    categories = [r['stage_name'] for r in stages]
    scheduled = [r['scheduled_hours'] for r in stages]
    gaps = [r['gap_hours'] for r in stages]

    option = {
        'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'shadow'}},
        'legend': {'data': ['Scheduled hours', 'Gap hours'], 'top': 0},
        'grid': {'left': 140, 'right': 24, 'top': 48, 'bottom': 32},
        'xAxis': {'type': 'value', 'name': 'Hours'},
        'yAxis': {'type': 'category', 'data': categories},
        'series': [
            {
                'name': 'Scheduled hours',
                'type': 'bar',
                'stack': 'utilization',
                'data': scheduled,
                'itemStyle': {'color': CHART_GOLD},
            },
            {
                'name': 'Gap hours',
                'type': 'bar',
                'stack': 'utilization',
                'data': gaps,
                'itemStyle': {'color': CHART_NEUTRAL},
            },
        ],
    }
    ui.echart(themed_chart_option(option)).classes('chart-height')
