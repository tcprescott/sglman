"""Schemas for the SpeedGaming sync endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SpeedGamingLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tournament_id: int
    event_slug: str
    content_type: Optional[str] = None
    active: bool
    sync_interval_minutes: int
    lookahead_hours: int
    last_synced_at: Optional[datetime] = None
    last_status: Optional[str] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SpeedGamingEpisodeResponse(BaseModel):
    """SG staging episode. The large raw ``payload`` blob is intentionally omitted."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_link_id: Optional[int] = None
    sg_episode_id: str
    title: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    content_hash: Optional[str] = None
    sync_status: str
    synced_at: Optional[datetime] = None
    sync_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SpeedGamingLinkCreateRequest(BaseModel):
    tournament_id: int
    event_slug: str
    content_type: Optional[str] = None
    sync_interval_minutes: int = 15
    lookahead_hours: int = 72
    active: bool = True


class SpeedGamingLinkUpdateRequest(BaseModel):
    event_slug: Optional[str] = None
    content_type: Optional[str] = None
    sync_interval_minutes: Optional[int] = None
    lookahead_hours: Optional[int] = None
    active: Optional[bool] = None


class SyncResultResponse(BaseModel):
    """Tally returned by an on-demand sync (``SyncResult.as_dict()``)."""

    imported: int
    unchanged: int
    skipped: int
    cancelled: int
    auto_finished: int
    errors: int
