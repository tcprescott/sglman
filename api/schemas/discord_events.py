"""Schemas for the Discord events endpoints (api/routers/discord_events.py)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DiscordEventTournamentResponse(BaseModel):
    """A tournament's Discord-events opt-in + templating settings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    discord_events_enabled: bool
    discord_event_duration_minutes: int
    discord_event_title_template: Optional[str] = None
    discord_event_description_template: Optional[str] = None


class DiscordScheduledEventResponse(BaseModel):
    """A single mirrored Discord Scheduled Event link row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    discord_event_id: int
    source_type: str
    source_id: int
    title: str
    content_hash: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class DiscordEventTournamentUpdateRequest(BaseModel):
    """Partial update of a tournament's Discord-events settings."""

    enabled: Optional[bool] = None
    duration_minutes: Optional[int] = None
    title_template: Optional[str] = None
    description_template: Optional[str] = None


class ReconcileResultResponse(BaseModel):
    """Tally of one on-demand reconcile pass (from ReconcileResult.as_dict())."""

    created: int
    updated: int
    cancelled: int
    unchanged: int
    errors: int
