"""Insights & Trends report.

Longitudinal view across events: crew participation trends, volunteer hours
over time, tournament health scorecards, and admin activity — all bucketed by
week or month. Complements the point-in-time snapshot reports.
"""

import asyncio
from datetime import date, timedelta
from typing import List, Optional

from nicegui import ui

from application.services import AnalyticsService
from application.utils.timezone import now_eastern
from .shared import (
    CHART_GOLD,
    CHART_NEUTRAL,
    CHART_RED,
    CHART_TEAL,
    csv_export_button,
    date_range_filter,
    eastern_bounds,
    navigate_with_params,
    parse_date,
    report_page_shell,
    themed_chart_option,
    tournament_filter,
)


# Default trailing window when no range is supplied: trends need history, so a
# single event weekend (the reports default) would collapse to one bucket.
DEFAULT_TREND_DAYS = 90


def _default_range(start: Optional[str], end: Optional[str]) -> tuple[date, date]:
    s = parse_date(start)
    e = parse_date(end)
    if s and e:
        return s, e
    today = now_eastern().date()
    return today - timedelta(days=DEFAULT_TREND_DAYS), today


def _normalize_bucket(bucket: Optional[str]) -> str:
    return 'month' if bucket == 'month' else 'week'


async def insights_page(
    start: Optional[str] = None,
    end: Optional[str] = None,
    bucket: Optional[str] = None,
    tournament_id: Optional[int] = None,
    **_unused,
) -> None:
    analytics = AnalyticsService()
    start_d, end_d = _default_range(start, end)
    bucket = _normalize_bucket(bucket)
    bounds_start, bounds_end = eastern_bounds(start_d, end_d)

    def nav(**overrides) -> None:
        params = {
            'report': 'insights',
            'start': start_d,
            'end': end_d,
            'bucket': bucket,
            'tournament_id': tournament_id,
        }
        params.update(overrides)
        navigate_with_params(**params)

    with report_page_shell('Insights & Trends'):
        with ui.card().classes('full-width q-pa-md'):
            with ui.row().classes('items-center gap-3'):
                date_range_filter(
                    start_d, end_d,
                    on_change=lambda s, e: nav(start=s, end=e),
                )
                bucket_select = ui.select(
                    options={'week': 'Weekly', 'month': 'Monthly'},
                    value=bucket,
                    label='Bucket',
                ).classes('control-width').props('dense')
                bucket_select.on(
                    'update:model-value',
                    lambda: nav(bucket=bucket_select.value),
                )
                await tournament_filter(
                    tournament_id,
                    on_change=lambda t_id: nav(tournament_id=t_id),
                )
            with ui.row().classes('q-mt-sm items-center gap-2'):
                ui.label('Range:').classes('text-caption')
                for days, label in ((30, 'Last 30d'), (90, 'Last 90d'), (365, 'Last year')):
                    today = now_eastern().date()
                    ui.button(
                        label,
                        on_click=lambda d=days, t=today: nav(start=t - timedelta(days=d), end=t),
                    ).props('flat dense')

        crew, hours, health, activity = await _load(analytics, bounds_start, bounds_end, bucket, tournament_id)

        # Volunteer shifts and audit logs are not tournament-scoped in the data
        # model, so the tournament filter only narrows the crew and health sections.
        scoped = tournament_id is not None
        _kpi_strip(crew, hours, health)
        _crew_section(crew, start_d, end_d)
        _volunteer_section(hours, start_d, end_d, scoped)
        _health_section(health, start_d, end_d)
        _activity_section(activity, scoped)


async def _load(analytics, start, end, bucket, tournament_id):
    return await asyncio.gather(
        analytics.crew_participation_trends(start, end, bucket, tournament_id=tournament_id),
        analytics.volunteer_hour_trends(start, end, bucket),
        analytics.tournament_health(start, end, tournament_id=tournament_id),
        analytics.activity_trends(start, end, bucket),
    )


# --- KPI strip ------------------------------------------------------------


def _kpi_strip(crew: dict, hours: dict, health: dict) -> None:
    scored = [r['health_score'] for r in health['rows'] if r['health_score'] is not None]
    avg_health = sum(scored) / len(scored) if scored else None
    approved = crew['totals']['commentator_approved'] + crew['totals']['tracker_approved']

    with ui.row().classes('full-width gap-3 q-mt-md items-stretch').style('flex-wrap: wrap;'):
        _kpi_card('Approved crew slots', f'{approved}',
                  f"{crew['totals']['unique_people']} unique people")
        _kpi_card('Volunteer hours', f"{hours['totals']['scheduled_hours']:g}",
                  f"{hours['totals']['checked_in_hours']:g}h checked in")
        _kpi_card('Tournaments scored', f"{len(scored)}",
                  f"of {len(health['rows'])} in window")
        _kpi_card('Avg health score',
                  f'{avg_health:.0f}' if avg_health is not None else '—',
                  'across scored tournaments',
                  color=_health_color(avg_health))


def _kpi_card(title: str, value: str, subtitle: str, color: str = 'primary') -> None:
    with ui.card().classes('q-pa-md').style('flex: 1 1 220px; min-width: 220px;'):
        ui.label(title).classes('text-caption text-grey-7')
        ui.label(value).classes('text-h4').style(f'color: var(--q-{color});')
        ui.label(subtitle).classes('text-caption')


# --- Crew participation ---------------------------------------------------


def _crew_section(crew: dict, start_d: date, end_d: date) -> None:
    labels = crew['bucket_labels']
    with ui.card().classes('chart-container q-pa-md'):
        ui.label('Crew participation over time').classes('text-h6')
        ui.label('Approved commentator & tracker slots per bucket, with unique people.') \
            .classes('italic-note')
        if not _has_signal(crew['commentator_approved'] + crew['tracker_approved'] + crew['unique_people']):
            ui.label('No crew activity in the selected window.').classes('italic-note q-mt-md')
        else:
            option = {
                'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'cross'}},
                'legend': {'data': ['Commentators', 'Trackers', 'Unique people'], 'top': 0},
                'grid': {'left': '3%', 'right': '4%', 'bottom': '3%', 'containLabel': True},
                'xAxis': {'type': 'category', 'data': labels},
                'yAxis': [
                    {'type': 'value', 'name': 'Approved slots'},
                    {'type': 'value', 'name': 'People', 'splitLine': {'show': False}},
                ],
                'series': [
                    {'name': 'Commentators', 'type': 'bar', 'stack': 'slots',
                     'data': crew['commentator_approved'], 'itemStyle': {'color': CHART_GOLD}},
                    {'name': 'Trackers', 'type': 'bar', 'stack': 'slots',
                     'data': crew['tracker_approved'], 'itemStyle': {'color': CHART_TEAL}},
                    {'name': 'Unique people', 'type': 'line', 'yAxisIndex': 1, 'smooth': True,
                     'data': crew['unique_people'], 'itemStyle': {'color': CHART_NEUTRAL},
                     'lineStyle': {'width': 2, 'color': CHART_NEUTRAL}},
                ],
            }
            ui.echart(themed_chart_option(option)).classes('chart-height')

    rows = [
        {
            'name': c['name'],
            'commentator_approved': c['commentator_approved'],
            'tracker_approved': c['tracker_approved'],
            'total_approved': c['total_approved'],
        }
        for c in crew['top_contributors']
    ]
    columns = [
        {'name': 'name', 'label': 'Contributor', 'field': 'name', 'sortable': True},
        {'name': 'commentator_approved', 'label': 'Commentary', 'field': 'commentator_approved', 'sortable': True},
        {'name': 'tracker_approved', 'label': 'Tracking', 'field': 'tracker_approved', 'sortable': True},
        {'name': 'total_approved', 'label': 'Total approved', 'field': 'total_approved', 'sortable': True},
    ]
    with ui.card().classes('full-width q-pa-md'):
        with ui.row().classes('items-center justify-between'):
            ui.label('Top crew contributors').classes('text-h6')
            csv_export_button(f'crew-contributors-{start_d}-to-{end_d}', lambda: columns, lambda: rows)
        if not rows:
            ui.label('No crew contributors in this window.').classes('italic-note')
        else:
            ui.table(columns=columns, rows=rows, pagination=15, row_key='name').classes('full-width')


# --- Volunteer hours ------------------------------------------------------


def _volunteer_section(hours: dict, start_d: date, end_d: date, scoped: bool = False) -> None:
    labels = hours['bucket_labels']
    with ui.card().classes('chart-container q-pa-md'):
        ui.label('Volunteer hours over time').classes('text-h6')
        ui.label('Scheduled vs checked-in volunteer-hours per bucket, with fill rate.') \
            .classes('italic-note')
        if scoped:
            ui.label('Event-wide — volunteer shifts are not tied to a tournament.') \
                .classes('italic-note')
        if not _has_signal(hours['scheduled_hours'] + hours['checked_in_hours']):
            ui.label('No volunteer hours in the selected window.').classes('italic-note q-mt-md')
        else:
            option = {
                'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'cross'}},
                'legend': {'data': ['Scheduled', 'Checked in', 'Fill rate %'], 'top': 0},
                'grid': {'left': '3%', 'right': '4%', 'bottom': '3%', 'containLabel': True},
                'xAxis': {'type': 'category', 'data': labels},
                'yAxis': [
                    {'type': 'value', 'name': 'Hours'},
                    {'type': 'value', 'name': 'Fill %', 'max': 100, 'splitLine': {'show': False}},
                ],
                'series': [
                    {'name': 'Scheduled', 'type': 'bar',
                     'data': hours['scheduled_hours'], 'itemStyle': {'color': CHART_GOLD}},
                    {'name': 'Checked in', 'type': 'bar',
                     'data': hours['checked_in_hours'], 'itemStyle': {'color': CHART_TEAL}},
                    {'name': 'Fill rate %', 'type': 'line', 'yAxisIndex': 1, 'smooth': True,
                     'data': hours['fill_rate'], 'itemStyle': {'color': CHART_NEUTRAL},
                     'lineStyle': {'width': 2, 'color': CHART_NEUTRAL}},
                ],
            }
            ui.echart(themed_chart_option(option)).classes('chart-height')

    rows = [
        {
            'name': v['name'],
            'scheduled_hours': v['scheduled_hours'],
            'checked_in_hours': v['checked_in_hours'],
            'shifts': v['shifts'],
        }
        for v in hours['top_volunteers']
    ]
    columns = [
        {'name': 'name', 'label': 'Volunteer', 'field': 'name', 'sortable': True},
        {'name': 'scheduled_hours', 'label': 'Scheduled h', 'field': 'scheduled_hours', 'sortable': True},
        {'name': 'checked_in_hours', 'label': 'Checked-in h', 'field': 'checked_in_hours', 'sortable': True},
        {'name': 'shifts', 'label': 'Shifts', 'field': 'shifts', 'sortable': True},
    ]
    with ui.card().classes('full-width q-pa-md'):
        with ui.row().classes('items-center justify-between'):
            ui.label('Top volunteers by hours').classes('text-h6')
            csv_export_button(f'volunteer-hours-{start_d}-to-{end_d}', lambda: columns, lambda: rows)
        if not rows:
            ui.label('No volunteer assignments in this window.').classes('italic-note')
        else:
            ui.table(columns=columns, rows=rows, pagination=15, row_key='name').classes('full-width')


# --- Tournament health ----------------------------------------------------


def _health_section(health: dict, start_d: date, end_d: date) -> None:
    rows = health['rows']
    scored = [r for r in rows if r['health_score'] is not None]

    with ui.card().classes('chart-container q-pa-md'):
        ui.label('Tournament health').classes('text-h6')
        ui.label('Composite 0–100 score from completion, on-time, crew coverage, and duration adherence.') \
            .classes('italic-note')
        if not scored:
            ui.label('No scoreable tournaments in the selected window.').classes('italic-note q-mt-md')
        else:
            ranked = sorted(scored, key=lambda r: r['health_score'])
            names = [r['tournament_name'] for r in ranked]
            data = [
                {'value': r['health_score'], 'itemStyle': {'color': _health_hex(r['health_score'])}}
                for r in ranked
            ]
            option = {
                'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'shadow'}},
                'grid': {'left': '3%', 'right': '6%', 'bottom': '3%', 'containLabel': True},
                'xAxis': {'type': 'value', 'name': 'Health', 'max': 100},
                'yAxis': {'type': 'category', 'data': names},
                'series': [{'name': 'Health score', 'type': 'bar', 'data': data}],
            }
            ui.echart(themed_chart_option(option)).classes('chart-height')

    display_rows = [
        {
            'tournament_name': r['tournament_name'],
            'health_score': r['health_score'] if r['health_score'] is not None else '—',
            'matches': f"{r['matches_finished']}/{r['matches_past']}",
            'completion_pct': _pct(r['completion_pct']),
            'on_time_pct': _pct(r['on_time_pct']),
            'coverage_pct': _pct(r['coverage_pct']),
            'avg_duration_min': _dur(r['avg_duration_min'], r['expected_avg_min']),
        }
        for r in rows
    ]
    columns = [
        {'name': 'tournament_name', 'label': 'Tournament', 'field': 'tournament_name', 'sortable': True},
        {'name': 'health_score', 'label': 'Health', 'field': 'health_score', 'sortable': True},
        {'name': 'matches', 'label': 'Finished/Past', 'field': 'matches'},
        {'name': 'completion_pct', 'label': 'Completion', 'field': 'completion_pct', 'sortable': True},
        {'name': 'on_time_pct', 'label': 'On-time', 'field': 'on_time_pct', 'sortable': True},
        {'name': 'coverage_pct', 'label': 'Crew coverage', 'field': 'coverage_pct', 'sortable': True},
        {'name': 'avg_duration_min', 'label': 'Avg dur (exp)', 'field': 'avg_duration_min'},
    ]
    csv_rows = [
        {
            'tournament_name': r['tournament_name'],
            'health_score': r['health_score'],
            'matches_total': r['matches_total'],
            'matches_past': r['matches_past'],
            'matches_finished': r['matches_finished'],
            'completion_pct': r['completion_pct'],
            'on_time_pct': r['on_time_pct'],
            'coverage_pct': r['coverage_pct'],
            'avg_start_delay_min': r['avg_start_delay_min'],
            'avg_duration_min': r['avg_duration_min'],
            'expected_avg_min': r['expected_avg_min'],
        }
        for r in rows
    ]
    csv_columns = [{'name': k, 'label': k, 'field': k} for k in (
        'tournament_name', 'health_score', 'matches_total', 'matches_past',
        'matches_finished', 'completion_pct', 'on_time_pct', 'coverage_pct',
        'avg_start_delay_min', 'avg_duration_min', 'expected_avg_min',
    )]
    with ui.card().classes('full-width q-pa-md'):
        with ui.row().classes('items-center justify-between'):
            ui.label('Health detail').classes('text-h6')
            csv_export_button(f'tournament-health-{start_d}-to-{end_d}', lambda: csv_columns, lambda: csv_rows)
        if not rows:
            ui.label('No tournaments with matches in this window.').classes('italic-note')
        else:
            ui.table(columns=columns, rows=display_rows, pagination=25, row_key='tournament_name') \
                .classes('full-width')


# --- Admin activity -------------------------------------------------------


def _activity_section(activity: dict, scoped: bool = False) -> None:
    labels = activity['bucket_labels']
    categories = activity['categories']
    with ui.card().classes('chart-container q-pa-md'):
        ui.label('Admin activity over time').classes('text-h6')
        ui.label('Audit-log actions per bucket, by top action category.').classes('italic-note')
        if scoped:
            ui.label('Event-wide — audit activity is not tied to a tournament.') \
                .classes('italic-note')
        if activity['total'] == 0:
            ui.label('No audit activity in the selected window.').classes('italic-note q-mt-md')
        else:
            # Palette holds three distinct series hues; keep the top three
            # categories and fold the long tail into a neutral "Other" stack.
            top = categories[:3]
            palette = [CHART_GOLD, CHART_TEAL, CHART_RED]
            series = []
            legend = []
            for i, cat in enumerate(top):
                series.append({
                    'name': cat['category'], 'type': 'bar', 'stack': 'actions',
                    'data': cat['counts'], 'itemStyle': {'color': palette[i]},
                })
                legend.append(cat['category'])
            if len(categories) > 3:
                other = [0] * len(labels)
                for cat in categories[3:]:
                    for i, v in enumerate(cat['counts']):
                        other[i] += v
                series.append({
                    'name': 'other', 'type': 'bar', 'stack': 'actions',
                    'data': other, 'itemStyle': {'color': CHART_NEUTRAL},
                })
                legend.append('other')
            option = {
                'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'shadow'}},
                'legend': {'data': legend, 'top': 0},
                'grid': {'left': '3%', 'right': '4%', 'bottom': '3%', 'containLabel': True},
                'xAxis': {'type': 'category', 'data': labels},
                'yAxis': {'type': 'value', 'name': 'Actions'},
                'series': series,
            }
            ui.echart(themed_chart_option(option)).classes('chart-height')


# --- Small helpers --------------------------------------------------------


def _has_signal(values: List) -> bool:
    return any(v for v in values)


def _pct(value: Optional[float]) -> str:
    return f'{value:.0f}%' if value is not None else '—'


def _dur(avg: Optional[float], expected: Optional[int]) -> str:
    if avg is None:
        return '—'
    if expected:
        return f'{avg:.0f} ({expected})'
    return f'{avg:.0f}'


def _health_hex(score: Optional[float]) -> str:
    if score is None:
        return CHART_NEUTRAL
    if score >= 75:
        return CHART_TEAL
    if score >= 50:
        return CHART_GOLD
    return CHART_RED


def _health_color(score: Optional[float]) -> str:
    if score is None:
        return 'primary'
    if score >= 75:
        return 'positive'
    if score >= 50:
        return 'warning'
    return 'negative'
