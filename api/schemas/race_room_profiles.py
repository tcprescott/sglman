"""Schemas for race room profile endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RaceRoomProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    goal: Optional[str] = None
    invitational: bool
    unlisted: bool
    auto_start: bool
    allow_comments: bool
    allow_midrace_chat: bool
    allow_non_entrant_chat: bool
    chat_message_delay: int
    start_delay: int
    time_limit: int
    streaming_required: bool
    created_at: datetime
    updated_at: datetime


class RaceRoomProfileCreateRequest(BaseModel):
    name: str
    goal: Optional[str] = None
    invitational: Optional[bool] = None
    unlisted: Optional[bool] = None
    auto_start: Optional[bool] = None
    allow_comments: Optional[bool] = None
    allow_midrace_chat: Optional[bool] = None
    allow_non_entrant_chat: Optional[bool] = None
    chat_message_delay: Optional[int] = None
    start_delay: Optional[int] = None
    time_limit: Optional[int] = None
    streaming_required: Optional[bool] = None


class RaceRoomProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    goal: Optional[str] = None
    invitational: Optional[bool] = None
    unlisted: Optional[bool] = None
    auto_start: Optional[bool] = None
    allow_comments: Optional[bool] = None
    allow_midrace_chat: Optional[bool] = None
    allow_non_entrant_chat: Optional[bool] = None
    chat_message_delay: Optional[int] = None
    start_delay: Optional[int] = None
    time_limit: Optional[int] = None
    streaming_required: Optional[bool] = None
