"""Schemas for player self-service availability endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from models import VolunteerAvailabilityStatus


class PlayerAvailabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    starts_at: datetime
    ends_at: datetime
    status: VolunteerAvailabilityStatus
    note: Optional[str] = None


class PlayerAvailabilityWindowInput(BaseModel):
    starts_at: datetime
    ends_at: datetime
    status: VolunteerAvailabilityStatus = VolunteerAvailabilityStatus.AVAILABLE
    note: Optional[str] = Field(default=None, max_length=1000)


class SetPlayerAvailabilityRequest(BaseModel):
    # Bounded so a single authenticated request cannot submit an unbounded
    # window list (request-body / storage exhaustion).
    windows: List[PlayerAvailabilityWindowInput] = Field(default_factory=list, max_length=500)
