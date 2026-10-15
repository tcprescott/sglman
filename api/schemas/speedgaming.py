"""Schemas for the SpeedGaming sync endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

_SLUG = "SpeedGaming event slug to pull episodes from."
_CONTENT_TYPE = "Optional SpeedGaming content type, to pull only one bracket of an event."
_INTERVAL = "Minutes between automatic syncs. Values below 1 are raised to 1."
_LOOKAHEAD = "How many hours ahead each sync looks for episodes. Values below 1 are raised to 1."


class SpeedGamingLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Event link id.")
    tournament_id: int = Field(..., description="The tournament synced episodes become matches in.")
    event_slug: str = Field(..., description=_SLUG)
    content_type: Optional[str] = Field(None, description=_CONTENT_TYPE)
    active: bool = Field(..., description="Whether the background sync picks this link up.")
    sync_interval_minutes: int = Field(..., description="Minutes between automatic syncs.")
    lookahead_hours: int = Field(..., description="How many hours ahead each sync looks for episodes.")
    last_synced_at: Optional[datetime] = Field(None, description="When the last sync ran (UTC). Null if never.")
    last_status: Optional[str] = Field(
        None,
        description="Outcome of the last sync: `ok`, `partial` (some episodes failed) or `error` (the fetch failed). Null if never synced.",
    )
    last_error: Optional[str] = Field(None, description="What went wrong on the last sync, when something did.")
    created_at: datetime = Field(..., description="When the link was created (UTC).")
    updated_at: datetime = Field(..., description="When the link last changed (UTC).")


class SpeedGamingEpisodeResponse(BaseModel):
    """SG staging episode. The large raw ``payload`` blob is intentionally omitted."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Staged episode id.")
    event_link_id: Optional[int] = Field(None, description="The event link that pulled it. Null if that link was deleted.")
    sg_episode_id: str = Field(..., description="SpeedGaming's own episode id.")
    title: Optional[str] = Field(None, description="Episode title from SpeedGaming.")
    scheduled_at: Optional[datetime] = Field(None, description="When the episode is scheduled (UTC).")
    content_hash: Optional[str] = Field(
        None, description="Fingerprint of the episode's content, used to skip unchanged episodes."
    )
    sync_status: str = Field(
        ...,
        description="Where the episode stands: `pending`, `synced` (its match is up to date), `skipped` (a finished or race-day match was left alone), `cancelled` (gone from SpeedGaming) or `error`.",
    )
    synced_at: Optional[datetime] = Field(None, description="When the episode was last written to its match (UTC).")
    sync_error: Optional[str] = Field(None, description="Why the last import failed, when `sync_status` is `error`.")
    created_at: datetime = Field(..., description="When the episode was first seen (UTC).")
    updated_at: datetime = Field(..., description="When the staged row last changed (UTC).")


class SpeedGamingLinkCreateRequest(BaseModel):
    tournament_id: int = Field(..., description="The tournament synced episodes become matches in.")
    event_slug: str = Field(..., description=_SLUG + " Must not already be linked to this tournament.")
    content_type: Optional[str] = Field(None, description=_CONTENT_TYPE)
    sync_interval_minutes: int = Field(15, description=_INTERVAL)
    lookahead_hours: int = Field(72, description=_LOOKAHEAD)
    active: bool = Field(True, description="Whether the background sync picks this link up.")


class SpeedGamingLinkUpdateRequest(BaseModel):
    """A partial edit. Omitted fields keep their current value."""

    event_slug: Optional[str] = Field(None, description=_SLUG)
    content_type: Optional[str] = Field(None, description=_CONTENT_TYPE + " An empty string clears it.")
    sync_interval_minutes: Optional[int] = Field(None, description=_INTERVAL)
    lookahead_hours: Optional[int] = Field(None, description=_LOOKAHEAD)
    active: Optional[bool] = Field(None, description="Whether the background sync picks this link up.")


class SyncResultResponse(BaseModel):
    """Tally returned by an on-demand sync (``SyncResult.as_dict()``)."""

    imported: int = Field(..., description="Episodes created or refreshed as matches.")
    unchanged: int = Field(..., description="Episodes whose content hadn't changed.")
    skipped: int = Field(..., description="Episodes left alone because their match is finished, in progress or has a race room.")
    cancelled: int = Field(..., description="Episodes gone from SpeedGaming, whose matches were detached.")
    auto_finished: int = Field(..., description="Matches marked finished because they were more than four hours past their start.")
    errors: int = Field(..., description="Episodes that failed to import, or 1 when the fetch itself failed.")
