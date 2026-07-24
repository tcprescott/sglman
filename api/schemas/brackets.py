"""Schemas for native bracket endpoints (thin wrappers over ``BracketService``).

Response models are ``from_attributes`` so ``BracketService`` ORM rows serialize
directly; enum fields (``format``, ``state``, ``status``) are typed as their
enums so FastAPI's JSON serialization emits the ``.value``.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from models import (
    BracketEntrantStatus,
    BracketEntryStatus,
    BracketFormat,
    BracketMatchGameState,
    BracketMatchState,
    BracketState,
)


class BracketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tournament_id: int
    name: str
    format: BracketFormat
    state: BracketState
    stage_order: int
    config: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class BracketEntrantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tournament_id: int
    display_name: str
    user_id: Optional[int] = None
    status: BracketEntrantStatus
    created_at: datetime
    updated_at: datetime


class BracketEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bracket_id: int
    entrant_id: int
    seed: Optional[int] = None
    group_number: Optional[int] = None
    final_rank: Optional[int] = None
    status: BracketEntryStatus
    created_at: datetime
    updated_at: datetime


class BracketMatchGameResponse(BaseModel):
    """One game of a bracket match's best-of-N series."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    bracket_match_id: int
    game_number: int
    match_id: Optional[int] = None
    winner_entry_id: Optional[int] = None
    forfeit: bool = False
    state: BracketMatchGameState
    cancelled_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BracketMatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bracket_id: int
    round: int
    position: int
    group_number: Optional[int] = None
    entry1_id: Optional[int] = None
    entry2_id: Optional[int] = None
    winner_id: Optional[int] = None
    entry1_score: Optional[int] = None
    entry2_score: Optional[int] = None
    forfeit: bool = False
    state: BracketMatchState
    winner_to_id: Optional[int] = None
    winner_to_slot: Optional[int] = None
    loser_to_id: Optional[int] = None
    loser_to_slot: Optional[int] = None
    # Per-matchup override; null means "use the round's best_of, else 1".
    best_of: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    # Empty until a game is scheduled — rows are created lazily, so a best-of-3
    # with one game played reports one game, not three.
    games: List[BracketMatchGameResponse] = []


# --- request bodies -------------------------------------------------------


class ScheduleGameRequest(BaseModel):
    """Schedule the next game of a series. The game number is server-assigned."""

    scheduled_date: str
    scheduled_time: str
    stream_room_id: Optional[int] = None
    comment: Optional[str] = None


class SetBestOfRequest(BaseModel):
    """Override one matchup's series length (null = fall back to the round)."""

    best_of: Optional[int] = None


class BracketCreateRequest(BaseModel):
    tournament_id: int
    name: str
    format: BracketFormat
    stage_order: int = 0
    config: Optional[Dict[str, Any]] = None


class EntrantCreateRequest(BaseModel):
    tournament_id: int
    display_name: str
    user_id: Optional[int] = None


class EnrollRequest(BaseModel):
    entrant_id: int
    seed: Optional[int] = None
    group_number: Optional[int] = None


class ReportResultRequest(BaseModel):
    winner_entry_id: int
    entry1_score: Optional[int] = None
    entry2_score: Optional[int] = None
    forfeit: bool = False


class AdvanceStageRequest(BaseModel):
    from_stage_order: int


__all__ = [
    'BracketResponse',
    'BracketEntrantResponse',
    'BracketEntryResponse',
    'BracketMatchGameResponse',
    'BracketMatchResponse',
    'ScheduleGameRequest',
    'SetBestOfRequest',
    'BracketCreateRequest',
    'EntrantCreateRequest',
    'EnrollRequest',
    'ReportResultRequest',
    'AdvanceStageRequest',
]
