"""Schemas for native bracket endpoints (thin wrappers over ``BracketService``).

Response models are ``from_attributes`` so ``BracketService`` ORM rows serialize
directly; enum fields (``format``, ``state``, ``status``) are typed as their
enums so FastAPI's JSON serialization emits the ``.value``.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from application.services.match.match_status import MatchStatus
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
    # The derived cross-surface status (docs/plans/bracket-match-integration-plan.md,
    # U1): what the web bracket paints and what the Discord DM says, so an API
    # consumer sees "live" while a game is being raced rather than having to
    # re-derive it from the games' Match timestamps. Populated on the list reads;
    # None where the matchup's games were not resolved.
    status: Optional[MatchStatus] = None
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


class StandingsRowResponse(BaseModel):
    """One entry's placement, with the entrant's name already joined in."""

    model_config = ConfigDict(from_attributes=True)

    entry_id: int
    entrant_id: int
    display_name: str
    seed: Optional[int] = None
    # `status` is this stage's participation; `entrant_status` is the
    # tournament-wide roster state. They move independently — dropping an
    # entrant does not cascade into the stage entry — so check both to render
    # "dropped".
    status: BracketEntryStatus
    entrant_status: BracketEntrantStatus
    rank: int
    # The persisted rank written at stage completion; null until then. It can
    # differ from `rank` when staff resolved a tie by hand.
    final_rank: Optional[int] = None
    points: float
    wins: int
    draws: int
    losses: int
    byes: int
    tiebreakers: Dict[str, float] = {}
    tied_with: List[int] = []


class StandingsGroupResponse(BaseModel):
    """One pool's ranked rows; ``group_number`` is null for a single pool."""

    model_config = ConfigDict(from_attributes=True)

    group_number: Optional[int] = None
    rows: List[StandingsRowResponse]


class ScheduleGameRequest(BaseModel):
    """Schedule the next game of a series. The game number is server-assigned."""

    scheduled_date: str
    scheduled_time: str
    stream_room_id: Optional[int] = None
    comment: Optional[str] = None


class LinkGameRequest(BaseModel):
    """Attach an existing scheduled ``Match`` to a matchup as its next game."""

    scheduled_match_id: int


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


class BracketUpdateRequest(BaseModel):
    """Edit a DRAFT bracket's definition. Omitted fields are left alone."""

    name: Optional[str] = None
    stage_order: Optional[int] = None
    config: Optional[Dict[str, Any]] = None


class RoundMetadataRequest(BaseModel):
    """Replace the per-round display metadata (``{round: {best_of, scheduled_at}}``).

    Null or empty clears it. Unlike the rest of the bracket definition this is
    editable after the stage has started — round chrome never touches the graph.
    """

    rounds: Optional[Dict[str, Any]] = None


class SetSeedsRequest(BaseModel):
    """Per-entry seeds (``entry_id → seed``); a null seed clears that entry's."""

    seeds: Dict[int, Optional[int]]


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
    'StandingsRowResponse',
    'StandingsGroupResponse',
    'ScheduleGameRequest',
    'SetBestOfRequest',
    'BracketCreateRequest',
    'BracketUpdateRequest',
    'RoundMetadataRequest',
    'SetSeedsRequest',
    'EntrantCreateRequest',
    'EnrollRequest',
    'ReportResultRequest',
    'AdvanceStageRequest',
]
