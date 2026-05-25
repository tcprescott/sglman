"""Reports summary dashboard.

KPI strip + report cards. All KPIs scoped to the configured event window.
"""

import asyncio
from typing import Optional

from nicegui import ui

from application.services import ReportsService, SystemConfigService
from application.utils.timezone import format_eastern_date, format_eastern_display
from .shared import (
    eastern_bounds,
    reports_url,
)


REPORT_CARDS = [
    {
        'key': 'capacity',
        'title': 'Capacity Forecast',
        'icon': 'show_chart',
        'description': 'Concurrent players across the event window vs configured capacity.',
    },
    {
        'key': 'match_ops',
        'title': 'Match Operations',
        'icon': 'timer',
        'description': 'Start delays, durations, and on-time rate per tournament.',
    },
    {
        'key': 'crew',
        'title': 'Staff / Crew Activity',
        'icon': 'groups',
        'description': 'Commentator and tracker coverage per match and per person.',
    },
    {
        'key': 'stream_rooms',
        'title': 'Stream Room Utilization',
        'icon': 'tv',
        'description': 'Hours scheduled per stage, gaps, and unplaced candidates.',
    },
    {
        'key': 'audit',
        'title': 'Audit Log',
        'icon': 'fact_check',
        'description': 'Filterable history of admin actions across the app.',
    },
]


async def dashboard_page() -> None:
    reports_service = ReportsService()

    with ui.column().classes('page-container-wide'):
        with ui.row().classes('header-row items-center'):
            ui.label('Reports').classes('page-title')
        ui.separator().classes('separator-spacing')

        ui.label('Event overview').classes('text-h6 q-mt-sm')

        start_d, end_d = await SystemConfigService.get_event_window()
        start, end = eastern_bounds(start_d, end_d)
        ui.label(
            f'Window: {format_eastern_date(start_d)} → {format_eastern_date(end_d)} (US/Eastern)'
        ).classes('italic-note')

        forecast, ops, coverage, utilization, max_stages = await asyncio.gather(
            reports_service.generate_capacity_forecast(start, end),
            reports_service.match_operations(start, end),
            reports_service.crew_coverage(start, end),
            reports_service.stream_room_utilization(start, end),
            SystemConfigService.get_max_concurrent_stages(),
        )

        # KPI computations
        peak_players = max(forecast['player_counts']) if forecast['player_counts'] else 0
        if peak_players > 0:
            peak_idx = forecast['player_counts'].index(peak_players)
            peak_time = forecast['intervals'][peak_idx]
        else:
            peak_time = None

        peak_stages = 0
        if forecast['intervals']:
            stage_counts = []
            for t in forecast['intervals']:
                used = sum(
                    1 for room in utilization['rooms']
                    if any(m['start'] <= t <= m['end'] for m in room['matches'])
                )
                stage_counts.append(used)
            peak_stages = max(stage_counts) if stage_counts else 0

        total_matches = len(ops['rows'])
        in_progress = sum(1 for r in ops['rows'] if r['state'] in ('Checked In', 'In Progress'))
        finished = sum(1 for r in ops['rows'] if r['state'] == 'Finished')

        candidate_rows = [r for r in coverage['coverage_rows'] if r['is_stream_candidate']]
        covered = sum(1 for r in candidate_rows if r['commentators_approved'] > 0 and r['trackers_approved'] > 0)
        coverage_pct = (covered / len(candidate_rows) * 100) if candidate_rows else None

        with ui.row().classes('full-width gap-3 q-mt-md no-wrap items-stretch') \
                .style('flex-wrap: wrap;'):
            _kpi_card(
                'Peak players',
                f'{peak_players} / {forecast["max_capacity"]}',
                _peak_subtitle(peak_time),
                color='primary' if peak_players <= forecast['max_capacity'] else 'negative',
            )
            _kpi_card(
                'Peak stages used',
                f'{peak_stages} / {max_stages}',
                'across the event window',
                color='primary' if peak_stages <= max_stages else 'negative',
            )
            _kpi_card(
                'Matches',
                f'{total_matches}',
                f'{in_progress} in flight • {finished} finished',
            )
            _kpi_card(
                'Stream candidate coverage',
                f'{coverage_pct:.0f}%' if coverage_pct is not None else '—',
                f'{covered}/{len(candidate_rows)} fully covered'
                if candidate_rows else 'no stream candidates in window',
                color='positive' if (coverage_pct or 0) >= 80 else 'warning',
            )

        ui.label('Reports').classes('text-h6 q-mt-lg')
        with ui.row().classes('full-width gap-3').style('flex-wrap: wrap;'):
            for card in REPORT_CARDS:
                _report_card(card)


def _kpi_card(title: str, value: str, subtitle: str, color: str = 'primary') -> None:
    with ui.card().classes('q-pa-md').style('flex: 1 1 220px; min-width: 220px;'):
        ui.label(title).classes('text-caption text-grey-7')
        ui.label(value).classes('text-h4').style(f'color: var(--q-{color});')
        ui.label(subtitle).classes('text-caption')


def _report_card(card: dict) -> None:
    with ui.card().classes('q-pa-md cursor-pointer').style('flex: 1 1 280px; min-width: 280px;') as box:
        with ui.row().classes('items-center no-wrap'):
            ui.icon(card['icon']).classes('text-h5 q-mr-sm')
            ui.label(card['title']).classes('text-h6')
        ui.label(card['description']).classes('text-body2 q-mt-xs')
        ui.link('Open report →', reports_url(report=card['key'])).classes('q-mt-sm')


def _peak_subtitle(peak_time) -> str:
    if peak_time is None:
        return 'no scheduled matches in window'
    return f'at {format_eastern_display(peak_time)}'
