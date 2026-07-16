"""Schemas for async qualifier live-race endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from api.schemas.async_qualifiers import AsyncQualifierRunResponse
from models import AsyncQualifierLiveRaceStatus

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
    created_at: datetime


class LiveRaceCreateRequest(BaseModel):
    pool_id: int
    match_title: str
    permalink_id: Optional[int] = None
    episode_id: Optional[int] = None
