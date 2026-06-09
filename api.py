
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from models import Match, GeneratedSeeds

# Create router with better OpenAPI metadata
router = APIRouter(
    tags=["Matches"],  # Tag for grouping in API docs
    responses={404: {"description": "Not found"}},  # Common responses
)


class UserBase(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    discord_id: Optional[int] = None
    pronouns: Optional[str] = None
    
    class Config:
        orm_mode = True


class TournamentBase(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    seed_generator: Optional[str] = None
    bracket_url: Optional[str] = None
    rules_url: Optional[str] = None
    tournament_format: Optional[str] = None
    average_match_duration: Optional[int] = None  # in minutes
    max_match_duration: Optional[int] = None  # in minutes
    
    class Config:
        orm_mode = True


class StreamRoomBase(BaseModel):
    id: int
    name: str
    stream_url: Optional[str] = None
    
    class Config:
        orm_mode = True


class GeneratedSeedBase(BaseModel):
    id: int
    seed_url: str
    seed_info: Optional[str] = None
    created_at: datetime
    
    class Config:
        orm_mode = True


class PlayerInfo(BaseModel):
    id: int
    user: UserBase
    finish_rank: Optional[int] = None
    assigned_station: Optional[str] = None
    
    class Config:
        orm_mode = True


class CommentatorInfo(BaseModel):
    id: int
    user: UserBase
    approved: bool
    
    class Config:
        orm_mode = True


class TrackerInfo(BaseModel):
    id: int
    user: UserBase
    approved: bool
    
    class Config:
        orm_mode = True


class MatchResponse(BaseModel):
    id: int
    tournament: TournamentBase
    title: Optional[str] = None
    stream_room: Optional[StreamRoomBase] = None
    generated_seed: Optional[GeneratedSeedBase] = None
    scheduled_at: Optional[datetime] = None
    seated_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    comment: Optional[str] = None
    players: List[PlayerInfo] = Field(default_factory=list)
    commentators: List[CommentatorInfo] = Field(default_factory=list)
    trackers: List[TrackerInfo] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


@router.get(
    "/matches", 
    response_model=List[MatchResponse],
    summary="Get tournament matches",
    description="Retrieve a list of matches with optional filtering by stream room(s) and date range. Includes related data for tournaments, players, and only approved commentators and trackers.",
    response_description="List of matches with filtered related data"
)
async def get_matches(
    match_id: Optional[List[int]] = Query(None, description="Filter matches by specific match IDs. Can provide multiple IDs."),
    stream_room_id: Optional[List[int]] = Query(None, description="Filter matches by specific stream room IDs. Can provide multiple IDs."),
    start_date: Optional[datetime] = Query(None, description="Filter matches scheduled on or after this date/time"),
    end_date: Optional[datetime] = Query(None, description="Filter matches scheduled before this date/time"),
    tournament_id: Optional[List[int]] = Query(None, description="Filter matches by specific tournament IDs. Can provide multiple IDs."),
    limit: int = Query(default=100, ge=1, le=500, description="Maximum number of matches to return")
):
    """
    Retrieve match information with related data and filtering options.

    ## Filters
    - **match_id**: Filter matches by specific match ID(s). Can provide multiple IDs.
    - **stream_room_id**: Filter matches by specific stream room(s). Can provide multiple IDs.
    - **start_date**: Filter matches scheduled on or after this date/time (ISO format)
    - **end_date**: Filter matches scheduled before this date/time (ISO format)
    - **tournament_id**: Filter matches by specific tournament(s). Can provide multiple IDs.
    - **limit**: Maximum number of matches to return (default: 100, max: 500)

    ## Response
    Returns matches with related data for:
    - Tournament information
    - Stream room details
    - Generated seed information (if available)
    - Players with user information
    - Approved commentators with user information (unapproved commentators are excluded)
    - Approved trackers with user information (unapproved trackers are excluded)

    ## Examples
    ```
    # Filter by a single stream room
    GET /api/matches?stream_room_id=1&start_date=2025-10-20T12:00:00

    # Filter by multiple stream rooms
    GET /api/matches?stream_room_id=1&stream_room_id=2&stream_room_id=3
    ```
    """
    query = Match.all()

    # Apply filters if provided
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

    # Load related data
    query = query.prefetch_related(
        'tournament',
        'stream_room',
        'generated_seed',
        'players__user',
        'commentators__user',
        'trackers__user'
    )

    # Order by scheduled_at and limit results
    matches = await query.order_by('scheduled_at').limit(limit)

    # Only approved commentators/trackers are public. Tortoise reverse relations
    # are read-only, so convert to the response model first and drop unapproved
    # crew there (response_model serialization never invokes a custom from_orm
    # under Pydantic v2).
    results = []
    for match in matches:
        resp = MatchResponse.model_validate(match, from_attributes=True)
        resp.commentators = [c for c in resp.commentators if c.approved]
        resp.trackers = [t for t in resp.trackers if t.approved]
        results.append(resp)

    return results
