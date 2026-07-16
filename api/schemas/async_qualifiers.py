"""Schemas for the async-qualifier endpoints (api/routers/async_qualifiers.py)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from models import AsyncQualifierReviewStatus, AsyncQualifierRunStatus


# --- Qualifiers -----------------------------------------------------------

class AsyncQualifierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    event_name: Optional[str] = None
    opens_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None
    runs_per_pool: int
    allowed_reattempts: int
    config: Optional[dict] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AsyncQualifierPublicResponse(BaseModel):
    """The player-facing public shell — name, window, and the run rules only.

    Deliberately omits ``config`` (internal draw-fairness / par-scoring knobs and
    messaging templates), which is admin-only: ``get_qualifier_for_player`` is
    ungated, so the ``/public`` route must not leak those internals the way the
    admin-gated ``AsyncQualifierResponse`` does.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    event_name: Optional[str] = None
    opens_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None
    runs_per_pool: int
    allowed_reattempts: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class QualifierCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    event_name: Optional[str] = None
    opens_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None
    runs_per_pool: int = 1
    allowed_reattempts: int = 0
    config: Optional[dict] = None


class QualifierUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    event_name: Optional[str] = None
    opens_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None
    runs_per_pool: Optional[int] = None
    allowed_reattempts: Optional[int] = None
    is_active: Optional[bool] = None
    config: Optional[dict] = None
    clear_window: bool = False


# --- Admins ---------------------------------------------------------------

class AdminRequest(BaseModel):
    user_id: int


# --- Pools ----------------------------------------------------------------

class AsyncQualifierPoolResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    qualifier_id: int
    name: str
    preset_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class PoolCreateRequest(BaseModel):
    name: str
    preset_id: Optional[int] = None


class PoolUpdateRequest(BaseModel):
    name: Optional[str] = None
    preset_id: Optional[int] = None
    clear_preset: bool = False


# --- Permalinks -----------------------------------------------------------

class AsyncQualifierPermalinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pool_id: int
    url: str
    notes: Optional[str] = None
    live_race: bool
    par_time: Optional[int] = None
    par_updated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PermalinkCreateRequest(BaseModel):
    url: str
    notes: Optional[str] = None
    live_race: bool = False


class PermalinkBulkRequest(BaseModel):
    urls: List[str] = Field(default_factory=list)


class PermalinkRollRequest(BaseModel):
    count: int


class PermalinkUpdateRequest(BaseModel):
    url: Optional[str] = None
    notes: Optional[str] = None
    live_race: Optional[bool] = None


# --- Runs -----------------------------------------------------------------

class AsyncQualifierRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    qualifier_id: int
    user_id: int
    permalink_id: Optional[int] = None
    live_race_id: Optional[int] = None
    status: AsyncQualifierRunStatus
    review_status: AsyncQualifierReviewStatus
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    elapsed_seconds: Optional[int] = None
    runner_vod_url: Optional[str] = None
    reattempted: bool
    reattempt_reason: Optional[str] = None
    score: Optional[float] = None
    reviewed_by_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    review_claimed_by_id: Optional[int] = None
    review_claimed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class StartRunRequest(BaseModel):
    pool_id: int


class SubmitRunRequest(BaseModel):
    elapsed_seconds: int
    runner_vod_url: Optional[str] = None


class ReattemptRequest(BaseModel):
    reason: str


class ReviewRequest(BaseModel):
    approved: bool
    note: Optional[str] = None


# --- Review notes ---------------------------------------------------------

class AsyncQualifierReviewNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    author_id: int
    note: str
    created_at: datetime


# --- Leaderboard ----------------------------------------------------------

class LeaderboardEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    username: str
    actual: float
    estimate: float
    slots_filled: int
    slots_total: int
