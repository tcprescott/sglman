"""Capacity Forecast detail report.

Concurrent player counts over a date range, against the configured capacity.
"""

from datetime import datetime, timedelta
from typing import Optional

from nicegui import ui

from application.services import ReportsService, SystemConfigService
from application.utils.timezone import format_eastern_display
from theme.tables.mobile_grid import enable_mobile_grid
from .shared import (
    CHART_GOLD,
    CHART_GOLD_AREA,
    CHART_GRID,
    CHART_RED,
    CHART_TEAL,
    CHART_TEXT,
    csv_export_button,
    date_range_filter,
    default_date_range,
    eastern_bounds,
    navigate_with_params,
    report_page_shell,
    themed_chart_option,
    tournament_filter,
)


async def capacity_page(
    start: Optional[str] = None,
    end: Optional[str] = None,
    tournament_id: Optional[int] = None,
    focus: Optional[str] = None,
    **_unused,
) -> None:
    reports_service = ReportsService()

    start_d, end_d = await default_date_range(start, end)
    focus_dt = _parse_focus(focus)

    with report_page_shell('Capacity Forecast'):
        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center gap-3'):
                date_range_filter(
                    start_d,
                    end_d,
                    on_change=lambda s, e: navigate_with_params(
                        report='capacity',
                        start=s,
                        end=e,
                        tournament_id=tournament_id,
                    ),
                )
                await tournament_filter(
                    tournament_id,
                    on_change=lambda t_id: navigate_with_params(
                        report='capacity',
                        start=start_d,
                        end=end_d,
                        tournament_id=t_id,
                    ),
                )

            event_start, event_end = await SystemConfigService.get_event_window()
            with ui.row().classes('q-mt-sm items-center gap-2'):
                ui.label('Shortcuts:').classes('text-caption')
                ui.button(
                    'Whole event',
                    on_click=lambda: navigate_with_params(
                        report='capacity',
                        start=event_start,
                        end=event_end,
                        tournament_id=tournament_id,
                    ),
                ).props('flat dense')
                for offset in range(0, (event_end - event_start).days + 1):
                    day_d = event_start + timedelta(days=offset)
                    if day_d > event_end:
                        break
                    ui.button(
                        day_d.strftime('%a %m-%d'),
                        on_click=lambda d=day_d: navigate_with_params(
                            report='capacity',
                            start=d,
                            end=d,
                            tournament_id=tournament_id,
                        ),
                    ).props('flat dense')

        bounds_start, bounds_end = eastern_bounds(start_d, end_d)
        forecast = await reports_service.generate_capacity_forecast(
            bounds_start, bounds_end, tournament_id=tournament_id,
        )

        intervals = forecast['intervals']
        player_counts = forecast['player_counts']
        on_stream_counts = forecast['on_stream_player_counts']
        capacity = forecast['max_capacity']

        with ui.card().classes('chart-container q-pa-md'):
            ui.label(
                f'Concurrent players ({forecast["interval_minutes"]}-minute intervals, capacity: {capacity})'
            ).classes('text-h6')

            time_labels = [t.strftime('%m-%d %H:%M ET') for t in intervals]
            capacity_series = [capacity] * len(intervals)

            # The slider ships in stock ECharts blue; restyle it to the gold
            # chrome so it sits with the palette in both modes.
            slider_style = {
                'fillerColor': 'rgba(181, 121, 28, 0.15)',
                'borderColor': CHART_GRID,
                'handleStyle': {'color': CHART_GOLD},
                'moveHandleStyle': {'color': CHART_GOLD},
                'textStyle': {'color': CHART_TEXT},
            }
            data_zoom_options = [{'type': 'inside'}, {'type': 'slider', **slider_style}]
            if focus_dt and intervals:
                first = intervals[0]
                last = intervals[-1]
                if first <= focus_dt <= last:
                    span = (last - first).total_seconds() or 1
                    center = (focus_dt - first).total_seconds() / span
                    half = 7200 / span  # ±2h window
                    data_zoom_options = [
                        {'type': 'inside', 'start': max(0, (center - half) * 100), 'end': min(100, (center + half) * 100)},
                        {'type': 'slider', **slider_style, 'start': max(0, (center - half) * 100), 'end': min(100, (center + half) * 100)},
                    ]

            echart_option = {
                'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'cross'}},
                'legend': {'data': ['Active players', 'On-stream players', 'Capacity'], 'top': 0},
                'grid': {'left': '3%', 'right': '4%', 'bottom': '14%', 'containLabel': True},
                'toolbox': {'feature': {'saveAsImage': {}, 'dataZoom': {}, 'restore': {}}},
                'dataZoom': data_zoom_options,
                'xAxis': {'type': 'category', 'boundaryGap': False, 'data': time_labels},
                'yAxis': [{'type': 'value', 'name': 'Players'}],
                'series': [
                    {
                        'name': 'Active players',
                        'type': 'line',
                        'data': player_counts,
                        'smooth': True,
                        'itemStyle': {'color': CHART_GOLD},
                        'areaStyle': {'color': CHART_GOLD_AREA},
                        'lineStyle': {'width': 2, 'color': CHART_GOLD},
                    },
                    {
                        'name': 'On-stream players',
                        'type': 'line',
                        'data': on_stream_counts,
                        'smooth': True,
                        'itemStyle': {'color': CHART_TEAL},
                        'lineStyle': {'width': 2, 'color': CHART_TEAL},
                    },
                    {
                        'name': 'Capacity',
                        'type': 'line',
                        'data': capacity_series,
                        'itemStyle': {'color': CHART_RED},
                        'lineStyle': {'width': 2, 'color': CHART_RED, 'type': 'dashed'},
                        'symbol': 'none',
                    },
                ],
            }
            ui.echart(themed_chart_option(echart_option)).classes('chart-height')

        with ui.card().classes('full-width q-mb-md q-pa-md'):
            ui.label('Top 5 peak times').classes('text-h6')
            peaks = ReportsService.peak_times(intervals, player_counts, top_n=5)
            if not peaks or peaks[0][1] == 0:
                ui.label('No matches found in the selected window.').classes('italic-note')
            else:
                for peak_time, count in peaks:
                    with ui.row().classes('items-center q-gutter-xs'):
                        ui.label(f'{format_eastern_display(peak_time)} — {count} players')
                        ui.link(
                            'Inspect',
                            f'/admin/reports?report=capacity'
                            f'&start={start_d.isoformat()}&end={end_d.isoformat()}'
                            + (f'&tournament_id={tournament_id}' if tournament_id else '')
                            + f'&focus={peak_time.isoformat()}',
                        ).classes('text-caption q-ml-sm')

        if focus_dt:
            with ui.card().classes('full-width q-pa-md'):
                ui.label(f'Matches active at {format_eastern_display(focus_dt)}').classes('text-h6')
                focused_matches = await reports_service.matches_active_at(focus_dt, tournament_id=tournament_id)
                if not focused_matches:
                    ui.label('No active matches at this instant.').classes('italic-note')
                else:
                    rows = [
                        {
                            'match_id': m.id,
                            'tournament': m.tournament.name if m.tournament else '',
                            'scheduled_at': format_eastern_display(m.scheduled_at),
                            'players': len(m.players),
                            'stream_room': m.stream_room.name if m.stream_room else '',
                            'state': m.current_state,
                        }
                        for m in focused_matches
                    ]
                    columns = [
                        {'name': 'match_id', 'label': 'Match', 'field': 'match_id', 'sortable': True},
                        {'name': 'tournament', 'label': 'Tournament', 'field': 'tournament', 'sortable': True},
                        {'name': 'scheduled_at', 'label': 'Scheduled', 'field': 'scheduled_at', 'sortable': True},
                        {'name': 'players', 'label': 'Players', 'field': 'players', 'sortable': True},
                        {'name': 'stream_room', 'label': 'Stream Room', 'field': 'stream_room'},
                        {'name': 'state', 'label': 'State', 'field': 'state'},
                    ]
                    focus_table = ui.table(columns=columns, rows=rows, row_key='match_id', pagination=25).classes('full-width')
                    enable_mobile_grid(focus_table, columns)

        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center justify-between'):
                ui.label('Forecast data').classes('text-h6')
                rows = [
                    {
                        'time': format_eastern_display(intervals[i]),
                        'active_players': player_counts[i],
                        'on_stream_players': on_stream_counts[i],
                        'match_ids': ','.join(str(m) for m in forecast['match_ids_per_interval'][i]),
                    }
                    for i in range(len(intervals))
                ]
                columns = [
                    {'name': 'time', 'label': 'Time', 'field': 'time', 'sortable': True},
                    {'name': 'active_players', 'label': 'Active players', 'field': 'active_players', 'sortable': True},
                    {'name': 'on_stream_players', 'label': 'On-stream players', 'field': 'on_stream_players', 'sortable': True},
                    {'name': 'match_ids', 'label': 'Match IDs', 'field': 'match_ids'},
                ]
                csv_export_button(
                    f'capacity-forecast-{start_d}-to-{end_d}',
                    lambda: columns,
                    lambda: rows,
                )
            forecast_table = ui.table(columns=columns, rows=rows, pagination=25, row_key='time').classes('full-width')
            enable_mobile_grid(forecast_table, columns)


def _parse_focus(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


