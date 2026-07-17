"""Schemas shared across multiple API domains."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from models import VolunteerAvailabilityStatus


class UserBase(BaseModel):
    """Public identity fields for a user appearing in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: Optional[str] = None
    discord_id: Optional[int] = None
    pronouns: Optional[str] = None


class AvailabilityWindowInput(BaseModel):
    """One availability window in a set-availability request.

    Shared by volunteer availability and player availability — the two use the
    same window shape and the same ``VolunteerAvailabilityStatus`` enum.
    """

    starts_at: datetime
    ends_at: datetime
    status: VolunteerAvailabilityStatus = VolunteerAvailabilityStatus.AVAILABLE
    note: Optional[str] = Field(default=None, max_length=1000)


class SetAvailabilityRequest(BaseModel):
    """Replace-all availability payload, bounded to guard against a single
    authenticated request submitting an unbounded window list."""

    windows: List[AvailabilityWindowInput] = Field(default_factory=list, max_length=500)
