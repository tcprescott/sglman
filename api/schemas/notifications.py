"""Schemas for tournament notification preference endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationPreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tournament_id: int
    match_notifications: str
    created_at: datetime
    updated_at: datetime


class NotificationPreferenceUpdate(BaseModel):
    tournament_id: int = Field(..., description="Tournament to set the preference for")
    match_notifications: str = Field(
        ..., description="One of: none, streamed, streamed_and_candidates, all"
    )
