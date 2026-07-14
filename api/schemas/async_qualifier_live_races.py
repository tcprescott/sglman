"""Schemas for async qualifier live-race endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from models import (
    AsyncQualifierLiveRaceStatus,
    AsyncQualifierReviewStatus,
    AsyncQualifierRunStatus,
)


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


class RunResponse(BaseModel):
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
    score: Optional[float] = None
    created_at: datetime


class LiveRaceCreateRequest(BaseModel):
    pool_id: int
    match_title: str
    permalink_id: Optional[int] = None
    episode_id: Optional[int] = None
