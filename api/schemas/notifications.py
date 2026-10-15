"""Schemas for tournament notification preference endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

_LEVEL_DESC = (
    "Which of the tournament's matches you hear about. One of: none (nothing), streamed "
    "(matches assigned to a stream stage), streamed_and_candidates (those plus matches "
    "marked as possible streams), all (every scheduled match)."
)


class NotificationPreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="The preference's ID.")
    tournament_id: int = Field(..., description="The tournament this preference follows.")
    match_notifications: str = Field(..., description=_LEVEL_DESC)
    created_at: datetime = Field(..., description="When the preference was first set (UTC).")
    updated_at: datetime = Field(..., description="When the preference was last changed (UTC).")


class NotificationPreferenceUpdate(BaseModel):
    tournament_id: int = Field(
        ..., description="The tournament to follow. You don't need to be signed up for it.",
    )
    match_notifications: str = Field(..., description=_LEVEL_DESC)
