"""Stream Room Utilization report.

Per-stage scheduled hours, gaps, back-to-back transitions, unplaced
stream-candidate count, plus a stacked-bar timeline.
"""

from typing import Optional

from nicegui import ui

from application.services import ReportsService
from application.utils.timezone import format_eastern_display
from .shared import (
    CHART_GOLD,
    CHART_NEUTRAL,
    csv_export_button,
    date_range_filter,
    default_date_range,
    eastern_bounds,
    navigate_with_params,
    parse_int,
    report_page_shell,
    tournament_filter,
)


async def stream_rooms_page(
    start: Optional[str] = None,
    end: Optional[str] = None,
    tournament_id: Optional[int] = None,
    stream_room_id: Optional[int] = None,
    **_unused,
) -> None:
    start_d, end_d = await default_date_range(start, end)
    stream_room_id_int = parse_int(stream_room_id)

    with report_page_shell('Stream Room Utilization'):
        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center gap-3'):
                date_range_filter(
                    start_d, end_d,
                    on_change=lambda s, e: navigate_with_params(
                        report='stream_rooms',
                        start=s, end=e,
                        tournament_id=tournament_id,
                        stream_room_id=stream_room_id_int,
                    ),
                )
                await tournament_filter(
                    tournament_id,
                    on_change=lambda t_id: navigate_with_params(
                        report='stream_rooms',
                        start=start_d, end=end_d,
                        tournament_id=t_id,
                        stream_room_id=stream_room_id_int,
                    ),
                )
                if stream_room_id_int is not None:
                    ui.button(
                        'Clear stream room filter', icon='close',
                        on_click=lambda: navigate_with_params(
                            report='stream_rooms',
                            start=start_d, end=end_d,
                            tournament_id=tournament_id,
                        ),
                    ).props('flat dense')

        bounds_start, bounds_end = eastern_bounds(start_d, end_d)
        data = await ReportsService().stream_room_utilization(
            bounds_start, bounds_end,
            tournament_id=tournament_id,
            stream_room_id=stream_room_id_int,
        )
        rooms = data['rooms']

        with ui.card().classes('chart-container q-pa-md'):
            ui.label('Hours scheduled per stream room').classes('text-h6')
            if not rooms:
                ui.label('No active stream rooms in the filter.').classes('italic-note')
            else:
                _render_utilization_chart(rooms)

        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center justify-between full-width'):
                ui.label(
                    f'Per-stream-room summary ({data["unplaced_candidate_count"]} '
                    f'unplaced stream candidate{"s" if data["unplaced_candidate_count"] != 1 else ""})'
                ).classes('text-h6')

                summary_rows = [
                    {
                        'stream_room_id': r['stream_room_id'],
                        'stream_room': r['stream_room_name'],
                        'matches': len(r['matches']),
                        'scheduled_hours': r['scheduled_hours'],
                        'gap_hours': r['gap_hours'],
                        'back_to_back': r['back_to_back_count'],
                    }
                    for r in rooms
                ]
                summary_columns = [
                    {'name': 'stream_room', 'label': 'Stream Room', 'field': 'stream_room', 'sortable': True},
                    {'name': 'matches', 'label': 'Matches', 'field': 'matches', 'sortable': True},
                    {'name': 'scheduled_hours', 'label': 'Scheduled hours', 'field': 'scheduled_hours', 'sortable': True},
                    {'name': 'gap_hours', 'label': 'Gap hours', 'field': 'gap_hours', 'sortable': True},
                    {'name': 'back_to_back', 'label': 'Back-to-back <15min', 'field': 'back_to_back', 'sortable': True},
                ]
                csv_export_button(
                    f'stream-room-utilization-{start_d}-to-{end_d}',
                    lambda: summary_columns,
                    lambda: summary_rows,
                )

            def _row_clicked(e):
                row = e.args[1] if isinstance(e.args, list) and len(e.args) > 1 else e.args
                rid = row.get('stream_room_id') if isinstance(row, dict) else None
                if rid:
                    navigate_with_params(
                        report='stream_rooms',
                        start=start_d, end=end_d,
                        tournament_id=tournament_id,
                        stream_room_id=rid,
                    )

            summary_table = ui.table(
                columns=summary_columns,
                rows=summary_rows,
                row_key='stream_room_id',
            ).classes('full-width')
            summary_table.on('row-click', _row_clicked)
            if stream_room_id_int is None:
                ui.label('Click a row to drill into a single stream room.').classes('italic-note')

        if stream_room_id_int is not None and rooms:
            with ui.card().classes('full-width q-pa-md'):
                ui.label(f'Matches on {rooms[0]["stream_room_name"]}').classes('text-h6')
                match_rows = [
                    {
                        'match_id': m['match_id'],
                        'tournament': m['tournament_name'],
                        'scheduled_at': format_eastern_display(m['scheduled_at']),
                        'start': format_eastern_display(m['start']),
                        'end': format_eastern_display(m['end']),
                    }
                    for m in rooms[0]['matches']
                ]
                match_columns = [
                    {'name': 'match_id', 'label': 'Match', 'field': 'match_id', 'sortable': True},
                    {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament', 'sortable': True},
                    {'name': 'scheduled_at', 'label': 'Scheduled', 'field': 'scheduled_at', 'sortable': True},
                    {'name': 'start', 'label': 'Window start', 'field': 'start', 'sortable': True},
                    {'name': 'end', 'label': 'Window end', 'field': 'end', 'sortable': True},
                ]
                ui.table(
                    columns=match_columns,
                    rows=match_rows,
                    pagination=25,
                    row_key='match_id',
                ).classes('full-width')


def _render_utilization_chart(rooms) -> None:
    """Horizontal bar of scheduled vs gap hours per stream room."""
    categories = [r['stream_room_name'] for r in rooms]
    scheduled = [r['scheduled_hours'] for r in rooms]
    gaps = [r['gap_hours'] for r in rooms]

    option = {
        'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'shadow'}},
        'legend': {'data': ['Scheduled hours', 'Gap hours']},
        'grid': {'left': 140, 'right': 24, 'top': 32, 'bottom': 32},
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
    ui.echart(option).classes('chart-height')
