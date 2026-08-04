"""Schemas for player self-service availability endpoints.

Player windows are read opt-out — see :mod:`api.routers.player_availability`.
The wire shape is the volunteer one, so ``status`` still defaults to
``available``; for a player that window is dropped on save, and the useful
values are ``unavailable`` and ``preferred``.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from api.schemas.common import AvailabilityWindowInput, SetAvailabilityRequest
from models import VolunteerAvailabilityStatus

# Player and volunteer availability share the window/set-request shapes.
PlayerAvailabilityWindowInput = AvailabilityWindowInput
SetPlayerAvailabilityRequest = SetAvailabilityRequest


class PlayerAvailabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    starts_at: datetime
    ends_at: datetime
    status: VolunteerAvailabilityStatus
    note: Optional[str] = None
