"""Schemas for the Discord events endpoints (api/routers/discord_events.py)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.snowflake import Snowflake

_TEMPLATE_KEYS = "Placeholders: `{tournament}`, `{match}` and `{players}`."


class DiscordEventTournamentResponse(BaseModel):
    """A tournament's Discord-events opt-in + templating settings."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Tournament id.")
    name: str = Field(..., description="Tournament name.")
    discord_events_enabled: bool = Field(
        ..., description="Whether this tournament's matches are mirrored as Discord events."
    )
    discord_event_duration_minutes: int = Field(..., description="Length given to each Discord event, in minutes.")
    discord_event_title_template: Optional[str] = Field(
        None, description="Event title template. Null uses `{match}`. " + _TEMPLATE_KEYS
    )
    discord_event_description_template: Optional[str] = Field(
        None, description="Event description template. Null uses `{tournament}: {players}`. " + _TEMPLATE_KEYS
    )


class DiscordScheduledEventResponse(BaseModel):
    """A single mirrored Discord Scheduled Event link row."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Link row id.")
    discord_event_id: Snowflake = Field(..., description="Discord's id for the scheduled event, as a string.")
    source_type: str = Field(..., description="What the event mirrors. Always `match` today.")
    source_id: int = Field(..., description="Id of the mirrored row, a match id when `source_type` is `match`.")
    title: str = Field(..., description="Title the event was last written with.")
    content_hash: Optional[str] = Field(
        None, description="Fingerprint of what was last written, used to skip unchanged events."
    )
    scheduled_at: Optional[datetime] = Field(None, description="Event start time (UTC).")
    synced_at: Optional[datetime] = Field(None, description="When the event was last written to Discord (UTC).")
    created_at: datetime = Field(..., description="When the event was first created (UTC).")
    updated_at: datetime = Field(..., description="When the link row last changed (UTC).")


class DiscordEventTournamentUpdateRequest(BaseModel):
    """Partial update of a tournament's Discord-events settings."""

    enabled: Optional[bool] = Field(None, description="Turn mirroring on or off for this tournament.")
    duration_minutes: Optional[int] = Field(
        None, description="Length of each event in minutes. Values below 1 are raised to 1."
    )
    title_template: Optional[str] = Field(
        None, description="Event title template. An empty string restores the default. " + _TEMPLATE_KEYS
    )
    description_template: Optional[str] = Field(
        None, description="Event description template. An empty string restores the default. " + _TEMPLATE_KEYS
    )


class ReconcileResultResponse(BaseModel):
    """Tally of one on-demand reconcile pass (from ReconcileResult.as_dict())."""

    created: int = Field(..., description="Discord events created.")
    updated: int = Field(..., description="Discord events rewritten because their match changed.")
    cancelled: int = Field(..., description="Discord events removed because their match left the schedule.")
    unchanged: int = Field(..., description="Discord events already up to date.")
    errors: int = Field(..., description="Events that failed to create, update or cancel.")
