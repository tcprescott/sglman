"""Match read endpoints."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api._match_view import MATCH_PREFETCH, serialize_match
from api.dependencies import ServiceErrorRoute, require_api_actor
from api.schemas.matches import MatchResponse
from models import Match

router = APIRouter(
    prefix="/matches",
    tags=["Matches"],
    route_class=ServiceErrorRoute,
    dependencies=[Depends(require_api_actor)],
)


@router.get(
    "",
    response_model=List[MatchResponse],
    summary="List matches",
    description=(
        "Retrieve matches with optional filtering by match, stream room, or "
        "tournament id and a scheduled-time range. Includes tournament, stream "
        "room, generated seed, players, and approved commentators/trackers."
    ),
)
async def get_matches(
    match_id: Optional[List[int]] = Query(None, description="Filter by specific match IDs."),
    stream_room_id: Optional[List[int]] = Query(None, description="Filter by specific stream room IDs."),
    start_date: Optional[datetime] = Query(None, description="Matches scheduled on or after this time."),
    end_date: Optional[datetime] = Query(None, description="Matches scheduled on or before this time."),
    tournament_id: Optional[List[int]] = Query(None, description="Filter by specific tournament IDs."),
    limit: int = Query(default=100, ge=1, le=500, description="Maximum matches to return."),
):
    query = Match.all()

    if match_id:
        query = query.filter(id__in=match_id)
    if stream_room_id:
        query = query.filter(stream_room_id__in=stream_room_id)
    if tournament_id:
        query = query.filter(tournament_id__in=tournament_id)
    if start_date is not None:
        query = query.filter(scheduled_at__gte=start_date)
    if end_date is not None:
        query = query.filter(scheduled_at__lte=end_date)

    query = query.prefetch_related(*MATCH_PREFETCH)
    matches = await query.order_by('scheduled_at').limit(limit)
    return [serialize_match(match) for match in matches]


@router.get(
    "/{match_id}",
    response_model=MatchResponse,
    summary="Get a single match",
)
async def get_match(match_id: int):
    match = await Match.filter(id=match_id).prefetch_related(*MATCH_PREFETCH).first()
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    return serialize_match(match)
