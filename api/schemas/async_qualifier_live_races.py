"""Schemas for async qualifier live-race endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.async_qualifiers import AsyncQualifierRunResponse
from models import AsyncQualifierLiveRaceStatus, AsyncQualifierRunStatus

# A live-race run and an async-qualifier run are the same row; serialize them the
# same way. ``RunResponse`` is retained as the name this router imports.
RunResponse = AsyncQualifierRunResponse


class LiveRaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pool_id: int
    match_title: str
    racetime_slug: Optional[str] = None
    status: AsyncQualifierLiveRaceStatus
    permalink_id: Optional[int] = None
    episode_id: Optional[int] = None
    # Racetime handles the last capture could not match to a user — staff's to-do
    # list, and the reason a racer can be missing from the results.
    unmatched_handles: Optional[List[str]] = None
    created_at: datetime


class LiveRaceCreateRequest(BaseModel):
    pool_id: int
    match_title: str
    permalink_id: Optional[int] = None
    episode_id: Optional[int] = None


class ManualResultRequest(BaseModel):
    """One racer's outcome, as a human asserts it."""

    user_id: int
    status: AsyncQualifierRunStatus
    # Required for a finisher, ignored for a forfeit or a disqualification — neither
    # has a time to score, and keeping one would put a scoreable-looking number on a
    # zero run.
    elapsed_seconds: Optional[int] = None


class ManualRecordRequest(BaseModel):
    """Record a live race's results by hand, when the room's event never arrived.

    The remedy for a dropped racetime connection: ``record_finish`` is reachable only
    from the inbound FINISHED event, so without this a missed event left the race
    stuck and its entrants unscored with nowhere to fix it.
    """

    results: List[ManualResultRequest] = Field(default_factory=list)
