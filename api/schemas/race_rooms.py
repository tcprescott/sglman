"""Schemas for the race room (racetime room lifecycle) endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from models import RaceRoomStatus


class RaceRoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    category: str
    room_name: Optional[str] = None
    status: RaceRoomStatus
    match_id: Optional[int] = None
    bot_id: Optional[int] = None
    opened_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class RaceRoomCreateRequest(BaseModel):
    match_id: int


class RaceRoomCancelRequest(BaseModel):
    reason: Optional[str] = None


class RaceRoomStatusUpdateRequest(BaseModel):
    status: RaceRoomStatus
