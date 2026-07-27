"""Compact result shapes for MCP tools.

Two rules decide whether a tool reuses an ``api/schemas`` model or gets a shape
here:

* **Singular reads reuse.** ``get_match`` returns the REST ``MatchResponse`` via
  the same serializer, so rules baked into it (notably: unapproved crew is not
  disclosed) cannot drift between the two surfaces.
* **List reads get a compact shape.** A hundred full match records is mostly
  padding, and padding is the expensive kind of wrong for an LLM consumer — it
  buries the answer and burns the context the model needs to reason. These
  models carry what identifies a row and what a person actually asks about.

Every datetime is UTC, as stored. Tools do not localize; the model is told once,
in the server instructions, rather than per field.
"""

from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# Declared once and shared, so every community-scoped tool describes its tenant
# argument identically. The description is the only place the model learns where
# a slug comes from, so it earns its keep in the schema of all ~20 tools.
TenantArg = Annotated[
    Optional[str],
    Field(description='Community slug, as returned by list_tenants. Required.'),
]


class TenantInfo(BaseModel):
    """A community the caller can address."""

    model_config = ConfigDict(from_attributes=True)

    slug: str = Field(description="Pass this as the `tenant` argument to other tools.")
    name: str
    roles: List[str] = Field(
        default_factory=list,
        description="Roles the caller holds in this community; empty means none.",
    )


class WhoAmI(BaseModel):
    """The caller's identity and reach, for orienting before any other call."""

    user_id: int
    username: str
    display_name: Optional[str] = None
    is_super_admin: bool
    tenants: List[TenantInfo] = Field(
        description="Communities the caller holds a role in, or all of them for a super admin."
    )


class TournamentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_active: bool
    tournament_format: Optional[str] = None
    players_per_match: Optional[int] = None
    event_start_date: Optional[datetime] = None
    event_end_date: Optional[datetime] = None


class StreamRoomInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_active: bool
    stream_url: Optional[str] = None


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: Optional[str] = None
    discord_id: Optional[int] = None
    is_active: bool = True


class UserDetail(UserSummary):
    """A user plus the roles they hold in the community being queried."""

    roles: List[str] = Field(default_factory=list)
    pronouns: Optional[str] = None
    twitch_username: Optional[str] = None
    racetime_username: Optional[str] = None


class CrewMemberInfo(BaseModel):
    """A crew signup, including unapproved ones — see the tool's gate."""

    id: int
    user: Optional[UserSummary] = None
    approved: bool
    acknowledged_at: Optional[datetime] = None


class MatchCrew(BaseModel):
    match_id: int
    commentators: List[CrewMemberInfo] = Field(default_factory=list)
    trackers: List[CrewMemberInfo] = Field(default_factory=list)


class StreamRoomBlock(BaseModel):
    """One stream room's slice of a day's schedule."""

    stream_room: Optional[str] = None
    matches: List['MatchSummary'] = Field(default_factory=list)


class ShiftSummary(BaseModel):
    """A volunteer shift and its staffing, without the full assignment rows."""

    id: int
    position: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    slots_needed: Optional[int] = None
    filled: int = 0
    assignees: List[str] = Field(default_factory=list)


class AuditEntry(BaseModel):
    id: int
    user_id: Optional[int] = None
    action: str
    details: Optional[object] = None
    created_at: datetime


class AuditPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[AuditEntry] = Field(default_factory=list)


class MatchSummary(BaseModel):
    """One match, at the detail level a scheduling question needs."""

    id: int
    tournament: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    status: str
    players: List[str] = Field(default_factory=list)
    stream_room: Optional[str] = None
    restream_url: Optional[str] = None


# StreamRoomBlock forward-references MatchSummary, which is declared after it.
StreamRoomBlock.model_rebuild()
