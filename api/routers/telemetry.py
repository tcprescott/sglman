"""Engagement telemetry endpoints — page views, interactions, and reach.

Staff only. ``TelemetryService`` re-checks that itself on every read, so the
HTTP dependency here is defence in depth rather than the only gate.
"""

from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query

from api.dependencies import ServiceErrorRoute, require_staff
from api.schemas.telemetry import TelemetrySummaryResponse, TelemetryTopRow
from application.services import TelemetryService
from models import User

router = APIRouter(prefix="/telemetry", tags=["Telemetry"], route_class=ServiceErrorRoute)

Dimension = Literal['paths', 'event_types', 'users', 'controls']

StartQuery = Query(None, description="Window start (UTC ISO 8601). Unbounded when omitted.")
EndQuery = Query(None, description="Window end (UTC ISO 8601). Unbounded when omitted.")


@router.get(
    "/summary",
    response_model=TelemetrySummaryResponse,
    summary="Engagement totals for a window (Staff only)",
    description=(
        "Counts telemetry rows, distinct people, distinct sessions and page loads recorded in the "
        "window. Leave `start` or `end` out to leave that side open.\n\n"
        "**Who can call this:** Staff."
    ),
)
async def summary(
    start: Optional[datetime] = StartQuery,
    end: Optional[datetime] = EndQuery,
    actor: User = Depends(require_staff),
):
    return await TelemetryService().engagement_summary(actor, start=start, end=end)


@router.get(
    "/top",
    response_model=List[TelemetryTopRow],
    summary="Top engagement rows for one dimension (Staff only)",
    description=(
        "Returns the busiest rows for one dimension, busiest first. The row shape depends on "
        "`dimension`: `paths` gives the most-loaded pages, `event_types` the most frequent event names, "
        "`users` the most active people and `controls` the most-used tabs, buttons, dialogs and fields.\n\n"
        "**Who can call this:** Staff."
    ),
)
async def top(
    dimension: Dimension = Query(..., description="Which leaderboard to return: `paths`, `event_types`, `users` or `controls`."),
    start: Optional[datetime] = StartQuery,
    end: Optional[datetime] = EndQuery,
    limit: int = Query(15, ge=1, le=100, description="Maximum rows to return."),
    actor: User = Depends(require_staff),
):
    service = TelemetryService()
    fn = {
        'paths': service.top_paths,
        'event_types': service.top_event_types,
        'users': service.top_users,
        'controls': service.top_controls,
    }[dimension]
    return await fn(actor, start=start, end=end, limit=limit)
