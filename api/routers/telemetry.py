"""Engagement telemetry endpoints — page views, interactions, and reach.

Staff only. ``TelemetryService`` re-checks that itself on every read, so the
HTTP dependency here is defence in depth rather than the only gate.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query

from api.dependencies import ServiceErrorRoute, require_staff
from application.services import TelemetryService
from models import User

router = APIRouter(prefix="/telemetry", tags=["Telemetry"], route_class=ServiceErrorRoute)

Dimension = Literal['paths', 'event_types', 'users']

StartQuery = Query(None, description="Window start (UTC ISO 8601). Unbounded when omitted.")
EndQuery = Query(None, description="Window end (UTC ISO 8601). Unbounded when omitted.")


@router.get(
    "/summary",
    response_model=Dict[str, Any],
    summary="Engagement totals for a window (Staff only)",
)
async def summary(
    start: Optional[datetime] = StartQuery,
    end: Optional[datetime] = EndQuery,
    actor: User = Depends(require_staff),
):
    return await TelemetryService().engagement_summary(actor, start=start, end=end)


@router.get(
    "/top",
    response_model=List[Dict[str, Any]],
    summary="Top engagement rows for one dimension (Staff only)",
)
async def top(
    dimension: Dimension = Query(..., description="Which leaderboard to return."),
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
    }[dimension]
    return await fn(actor, start=start, end=end, limit=limit)
