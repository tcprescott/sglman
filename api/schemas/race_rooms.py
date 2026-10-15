"""Schemas for the race room (racetime room lifecycle) endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from models import RaceRoomStatus

_STATUS = (
    "Room state as Wizzrobe last recorded it: `open`, `in_progress`, `finished` or `cancelled`."
)


class RaceRoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Race room id.")
    slug: str = Field(
        ..., description="racetime.gg room slug (`<category>/<room>`). The room lives at `https://racetime.gg/<slug>`."
    )
    category: str = Field(..., description="racetime.gg category the room was opened in.")
    room_name: Optional[str] = Field(None, description="Name Wizzrobe gave the room, usually the match title.")
    status: RaceRoomStatus = Field(..., description=_STATUS)
    match_id: Optional[int] = Field(
        None, description="The match this room is for. Null if that match was deleted."
    )
    bot_id: Optional[int] = Field(
        None, description="The racetime bot that opened the room. Null if that bot was removed."
    )
    opened_at: Optional[datetime] = Field(None, description="When the room opened (UTC).")
    created_at: datetime = Field(..., description="When Wizzrobe recorded the room (UTC).")
    updated_at: datetime = Field(..., description="When the record last changed (UTC).")


class RaceRoomCreateRequest(BaseModel):
    match_id: int = Field(..., description="The match to open a room for.")


class RaceRoomCancelRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Optional reason, kept in the audit log.")


class RaceRoomStatusUpdateRequest(BaseModel):
    status: RaceRoomStatus = Field(..., description="New state: `open`, `in_progress`, `finished` or `cancelled`.")
