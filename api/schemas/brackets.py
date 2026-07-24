"""Schemas for native bracket endpoints (thin wrappers over ``BracketService``).

Response models are ``from_attributes`` so ``BracketService`` ORM rows serialize
directly; enum fields (``format``, ``state``, ``status``) are typed as their
enums so FastAPI's JSON serialization emits the ``.value``.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict

from models import (
    BracketEntrantStatus,
    BracketEntryStatus,
    BracketFormat,
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
    state: BracketMatchState
    winner_to_id: Optional[int] = None
    winner_to_slot: Optional[int] = None
    loser_to_id: Optional[int] = None
    loser_to_slot: Optional[int] = None
    match_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


# --- request bodies -------------------------------------------------------


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


class AdvanceStageRequest(BaseModel):
    from_stage_order: int


__all__ = [
    'BracketResponse',
    'BracketEntrantResponse',
    'BracketEntryResponse',
    'BracketMatchResponse',
    'BracketCreateRequest',
    'EntrantCreateRequest',
    'EnrollRequest',
    'ReportResultRequest',
    'AdvanceStageRequest',
]
