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
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class MatchSummary(BaseModel):
    """One match, at the detail level a scheduling question needs."""

    id: int
    tournament: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    status: str
    players: List[str] = Field(default_factory=list)
    stream_room: Optional[str] = None
    restream_url: Optional[str] = None
