"""Schemas for race room profile endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

_GOAL = "racetime.gg goal for rooms opened with this profile. Null falls back to the tournament's own goal."
_INVITATIONAL = "Whether the room is invite-only."
_UNLISTED = "Whether the room is hidden from racetime.gg's public race list."
_AUTO_START = "Whether the race starts on its own once every entrant is ready."
_ALLOW_COMMENTS = "Whether entrants may leave a comment when they finish."
_ALLOW_MIDRACE = "Whether chat stays open while the race is running."
_ALLOW_NON_ENTRANT = "Whether people who aren't racing may chat."
_CHAT_DELAY = "Delay, in seconds, before chat messages appear. Zero or more."
_START_DELAY = "Countdown, in seconds, before an auto-started race begins. Zero or more."
_TIME_LIMIT = "Hours before the room closes on its own. Zero or more."
_STREAMING = "Whether entrants must be streaming to join."


class RaceRoomProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Profile id.")
    name: str = Field(..., description="Profile name, unique in this community.")
    goal: Optional[str] = Field(None, description=_GOAL)
    invitational: bool = Field(..., description=_INVITATIONAL)
    unlisted: bool = Field(..., description=_UNLISTED)
    auto_start: bool = Field(..., description=_AUTO_START)
    allow_comments: bool = Field(..., description=_ALLOW_COMMENTS)
    allow_midrace_chat: bool = Field(..., description=_ALLOW_MIDRACE)
    allow_non_entrant_chat: bool = Field(..., description=_ALLOW_NON_ENTRANT)
    chat_message_delay: int = Field(..., description=_CHAT_DELAY)
    start_delay: int = Field(..., description=_START_DELAY)
    time_limit: int = Field(..., description=_TIME_LIMIT)
    streaming_required: bool = Field(..., description=_STREAMING)
    created_at: datetime = Field(..., description="When the profile was created (UTC).")
    updated_at: datetime = Field(..., description="When the profile was last changed (UTC).")


class RaceRoomProfileCreateRequest(BaseModel):
    """A new profile. Omitted settings take the defaults noted on each field."""

    name: str = Field(..., description="Profile name, unique in this community.")
    goal: Optional[str] = Field(None, description=_GOAL)
    invitational: Optional[bool] = Field(None, description=_INVITATIONAL + " Defaults to false.")
    unlisted: Optional[bool] = Field(None, description=_UNLISTED + " Defaults to false.")
    auto_start: Optional[bool] = Field(None, description=_AUTO_START + " Defaults to true.")
    allow_comments: Optional[bool] = Field(None, description=_ALLOW_COMMENTS + " Defaults to true.")
    allow_midrace_chat: Optional[bool] = Field(None, description=_ALLOW_MIDRACE + " Defaults to true.")
    allow_non_entrant_chat: Optional[bool] = Field(None, description=_ALLOW_NON_ENTRANT + " Defaults to true.")
    chat_message_delay: Optional[int] = Field(None, description=_CHAT_DELAY + " Defaults to 0.")
    start_delay: Optional[int] = Field(None, description=_START_DELAY + " Defaults to 15.")
    time_limit: Optional[int] = Field(None, description=_TIME_LIMIT + " Defaults to 24.")
    streaming_required: Optional[bool] = Field(None, description=_STREAMING + " Defaults to false.")


class RaceRoomProfileUpdateRequest(BaseModel):
    """A partial edit. Omitted or null fields keep their current value."""

    name: Optional[str] = Field(None, description="New profile name, unique in this community.")
    goal: Optional[str] = Field(None, description=_GOAL + " An empty string clears it.")
    invitational: Optional[bool] = Field(None, description=_INVITATIONAL)
    unlisted: Optional[bool] = Field(None, description=_UNLISTED)
    auto_start: Optional[bool] = Field(None, description=_AUTO_START)
    allow_comments: Optional[bool] = Field(None, description=_ALLOW_COMMENTS)
    allow_midrace_chat: Optional[bool] = Field(None, description=_ALLOW_MIDRACE)
    allow_non_entrant_chat: Optional[bool] = Field(None, description=_ALLOW_NON_ENTRANT)
    chat_message_delay: Optional[int] = Field(None, description=_CHAT_DELAY)
    start_delay: Optional[int] = Field(None, description=_START_DELAY)
    time_limit: Optional[int] = Field(None, description=_TIME_LIMIT)
    streaming_required: Optional[bool] = Field(None, description=_STREAMING)
