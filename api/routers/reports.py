"""Reporting endpoints — the programmatic peer of the Admin → Reports tab.

Every route is admin (``can_view_admin``: staff, tournament admin, or crew
coordinator), which is the tab's own gate. Reads only, so a read-only token
works throughout.

Two reports are **reshaped rather than passed through**. ``ReportsService``
builds its payloads for a chart that is about to draw them, so they carry
per-interval and per-match detail — ``stage_utilization``'s even contains
ORM ``Match`` rows, which have no serializable form. ``capacity_forecast``
returns peaks and headroom instead of the full series, and
``stage_utilization`` per-stage totals instead of every booking. The MCP
tools in ``mcpserver/tools/analytics.py`` make the same call for the same
reason; the two surfaces answer identically on purpose.

``volunteer_hour_trends`` carries the ``VOLUNTEERS`` flag at the route rather
than the router: ``AnalyticsService`` has no flag of its own, so without it a
community with volunteers switched off could still read its volunteer hours
here.
"""

from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query

from api.dependencies import ServiceErrorRoute, require_admin, require_feature
from api.schemas.reports import (
    ActiveMatchRow,
    CapacityForecastResponse,
    CapacityPeak,
    ReportPayload,
    ReportRows,
    StageUtilizationResponse,
    StageUtilizationRow,
)
from application.services import AnalyticsService, ReportsService
from models import FeatureFlag

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
    route_class=ServiceErrorRoute,
    dependencies=[Depends(require_admin)],
)

# How many busiest intervals a forecast reports — enough to see the shape of a
# day's peak, short enough that the answer is still readable.
FORECAST_PEAKS = 5

Bucket = Literal['week', 'month']

StartQuery = Query(..., description="Window start (UTC ISO 8601).")
EndQuery = Query(..., description="Window end (UTC ISO 8601).")


def _window(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    if end < start:
        raise ValueError("end must not be before start.")
    return start, end


@router.get(
    "/capacity-forecast",
    response_model=CapacityForecastResponse,
    summary="Concurrent-player load against the configured capacity",
)
async def capacity_forecast(
    start: datetime = StartQuery,
    end: datetime = EndQuery,
    tournament_id: Optional[int] = Query(None, description="Limit to one tournament."),
):
    start, end = _window(start, end)
    service = ReportsService()
    raw = await service.generate_capacity_forecast(
        start=start, end=end, tournament_id=tournament_id,
    )
    counts = raw['player_counts']
    capacity = raw['max_capacity']
    return CapacityForecastResponse(
        start=raw['start'],
        end=raw['end'],
        interval_minutes=raw['interval_minutes'],
        max_capacity=capacity,
        peak_players=max(counts, default=0),
        peak_on_stream_players=max(raw['on_stream_player_counts'], default=0),
        over_capacity_intervals=sum(1 for c in counts if capacity and c > capacity),
        busiest=[
            CapacityPeak(at=at, players=players)
            for at, players in service.peak_times(
                raw['intervals'], counts, top_n=FORECAST_PEAKS,
            )
        ],
    )


@router.get(
    "/stage-utilization",
    response_model=StageUtilizationResponse,
    summary="How hard each stage is worked over a window",
)
async def stage_utilization(
    start: datetime = StartQuery,
    end: datetime = EndQuery,
    tournament_id: Optional[int] = Query(None, description="Limit to one tournament."),
    stage_id: Optional[int] = Query(None, description="Limit to one stage."),
):
    start, end = _window(start, end)
    raw = await ReportsService().stage_utilization(
        start=start, end=end,
        tournament_id=tournament_id, stage_id=stage_id,
    )
    return StageUtilizationResponse(
        stages=[
            StageUtilizationRow(
                stage_id=stage['stage_id'],
                stage_name=stage['stage_name'],
                scheduled_hours=stage['scheduled_hours'],
                match_count=len(stage['matches']),
                gap_hours=stage['gap_hours'],
                back_to_back_count=stage['back_to_back_count'],
            )
            for stage in raw['stages']
        ],
        unplaced_candidate_count=raw['unplaced_candidate_count'],
    )


@router.get(
    "/match-operations",
    response_model=ReportPayload,
    summary="Per-tournament match operations: scheduling, lifecycle, punctuality",
)
async def match_operations(
    start: datetime = StartQuery,
    end: datetime = EndQuery,
    tournament_id: Optional[int] = Query(None, description="Limit to one tournament."),
):
    start, end = _window(start, end)
    return await ReportsService().match_operations(
        start=start, end=end, tournament_id=tournament_id,
    )


@router.get(
    "/crew-coverage",
    response_model=ReportPayload,
    summary="Per-match crew coverage and per-person contribution",
)
async def crew_coverage(
    start: datetime = StartQuery,
    end: datetime = EndQuery,
    tournament_id: Optional[int] = Query(None, description="Limit to one tournament."),
    user_id: Optional[int] = Query(None, description="Limit to one crew member."),
    approved_only: bool = Query(
        False, description="Count only approved signups toward the hours total."
    ),
):
    start, end = _window(start, end)
    return await ReportsService().crew_coverage(
        start=start, end=end, tournament_id=tournament_id,
        user_id=user_id, approved_only=approved_only,
    )


@router.get(
    "/matches-active-at",
    response_model=List[ActiveMatchRow],
    summary="Which matches are in progress at one moment",
)
async def matches_active_at(
    instant: datetime = Query(..., description="The moment to look at (UTC ISO 8601)."),
    tournament_id: Optional[int] = Query(None, description="Limit to one tournament."),
    limit: int = Query(50, ge=1, le=200, description="Maximum matches to return."),
):
    matches = await ReportsService().matches_active_at(
        instant=instant, tournament_id=tournament_id,
    )
    return [
        ActiveMatchRow(
            match_id=match.id,
            tournament=match.tournament.name if match.tournament else None,
            scheduled_at=match.scheduled_at,
            players=[p.user.preferred_name for p in match.players if p.user],  # type: ignore[attr-defined]
            stage=match.stage.name if match.stage else None,
        )
        for match in matches[:limit]
    ]


@router.get(
    "/tournament-health",
    response_model=ReportRows,
    summary="Per-tournament health scorecards",
)
async def tournament_health(
    start: datetime = StartQuery,
    end: datetime = EndQuery,
    tournament_id: Optional[int] = Query(None, description="Limit to one tournament."),
):
    start, end = _window(start, end)
    report = await AnalyticsService().tournament_health(
        start=start, end=end, tournament_id=tournament_id,
    )
    return report['rows']


@router.get(
    "/crew-participation-trends",
    response_model=ReportPayload,
    summary="Crew signups versus approvals over time",
)
async def crew_participation_trends(
    start: datetime = StartQuery,
    end: datetime = EndQuery,
    bucket: Bucket = Query('week', description="Bucket size."),
    tournament_id: Optional[int] = Query(None, description="Limit to one tournament."),
):
    start, end = _window(start, end)
    return await AnalyticsService().crew_participation_trends(
        start=start, end=end, bucket=bucket, tournament_id=tournament_id,
    )


@router.get(
    "/activity-trends",
    response_model=ReportPayload,
    summary="Audit-log volume over time, grouped by action namespace",
)
async def activity_trends(
    start: datetime = StartQuery,
    end: datetime = EndQuery,
    bucket: Bucket = Query('week', description="Bucket size."),
):
    start, end = _window(start, end)
    return await AnalyticsService().activity_trends(start=start, end=end, bucket=bucket)


@router.get(
    "/volunteer-hour-trends",
    response_model=ReportPayload,
    summary="Scheduled versus checked-in volunteer hours over time",
    dependencies=[Depends(require_feature(FeatureFlag.VOLUNTEERS))],
)
async def volunteer_hour_trends(
    start: datetime = StartQuery,
    end: datetime = EndQuery,
    bucket: Bucket = Query('week', description="Bucket size."),
):
    start, end = _window(start, end)
    return await AnalyticsService().volunteer_hour_trends(
        start=start, end=end, bucket=bucket,
    )
