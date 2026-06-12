"""Request schemas for match write actions."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class MatchCreateRequest(BaseModel):
    tournament_id: int
    scheduled_date: str = Field(..., description="Eastern date, YYYY-MM-DD")
    scheduled_time: str = Field(..., description="Eastern time, HH:MM")
    player_ids: List[int] = Field(..., min_length=1, description="User IDs of the players")
    comment: Optional[str] = None
    stream_room_id: Optional[int] = None
    commentator_ids: Optional[List[int]] = None
    tracker_ids: Optional[List[int]] = None
    is_stream_candidate: bool = False


class MatchRequestCreate(BaseModel):
    """Player-initiated match request. The caller must be among ``player_ids``."""

    tournament_id: int
    scheduled_date: str = Field(..., description="Eastern date, YYYY-MM-DD")
    scheduled_time: str = Field(..., description="Eastern time, HH:MM")
    player_ids: List[int] = Field(..., min_length=1)
    comment: Optional[str] = None


class MatchUpdateRequest(BaseModel):
    tournament_id: Optional[int] = None
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None
    player_ids: Optional[List[int]] = None
    commentator_ids: Optional[List[int]] = None
    tracker_ids: Optional[List[int]] = None
    comment: Optional[str] = None
    clear_seated: bool = False
    clear_started: bool = False
    clear_finished: bool = False
    clear_confirmed: bool = False
    clear_seed: bool = False


class StreamCandidateRequest(BaseModel):
    flag: bool = Field(..., description="Set or clear the stream-candidate flag")


class AssignStageRequest(BaseModel):
    stream_room_id: Optional[int] = Field(None, description="Stream room to assign, or null to clear")


class AssignStationsRequest(BaseModel):
    assignments: Dict[int, Optional[str]] = Field(
        ..., description="Map of MatchPlayers id -> station label (or null to clear)"
    )


class RecordResultRequest(BaseModel):
    winner_id: int = Field(..., description="The MatchPlayers row id of the winner")


class CrewSignupRequest(BaseModel):
    role: str = Field(..., description="'commentator' or 'tracker'")


class SeedResultResponse(BaseModel):
    message: str
    seed_url: Optional[str] = None


class MatchSuggestionResponse(BaseModel):
    suggested_at: datetime = Field(..., description="Suggested match start time (UTC)")
