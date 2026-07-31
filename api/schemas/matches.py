"""Response schemas for match-related endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common import UserBase


class TournamentBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    seed_generator: Optional[str] = None
    bracket_url: Optional[str] = None
    rules_url: Optional[str] = None
    tournament_format: Optional[str] = None
    average_match_duration: Optional[int] = None  # in minutes
    max_match_duration: Optional[int] = None  # in minutes


class StreamRoomBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    stream_url: Optional[str] = None


class GeneratedSeedBase(BaseModel):
    """A rolled seed and its provenance.

    ``settings_snapshot`` is the settings as sent to the randomizer at roll time,
    which is what answers "what settings did this seed use?" after the preset has
    since been edited. Exposed on the authenticated match read only — a
    spoiler-adjacent setting is precisely what a viewer must not see mid-race.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    seed_url: str
    seed_info: Optional[str] = None
    randomizer: Optional[str] = None
    settings_snapshot: Optional[dict] = None
    provider_meta: Optional[dict] = None
    created_at: datetime


class PlayerInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user: UserBase
    finish_rank: Optional[int] = None
    assigned_station: Optional[str] = None


class CommentatorInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user: UserBase
    approved: bool


class TrackerInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user: UserBase
    approved: bool


class MatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tournament: TournamentBase
    title: Optional[str] = None
    stream_room: Optional[StreamRoomBase] = None
    generated_seed: Optional[GeneratedSeedBase] = None
    scheduled_at: Optional[datetime] = None
    seated_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    comment: Optional[str] = None
    # The proctor's dispute flag and their note. Confirming clears the flag and
    # keeps the note, so a confirmed match can carry a note with the flag off.
    needs_review: bool = False
    review_note: Optional[str] = None
    players: List[PlayerInfo] = Field(default_factory=list)
    commentators: List[CommentatorInfo] = Field(default_factory=list)
    trackers: List[TrackerInfo] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
