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


class OperationResult(BaseModel):
    """The outcome of a write that has no record to hand back.

    Deliberately not a bare string: a tool must return a typed model or the SDK
    ships its result as an untyped text blob, and the model is then left parsing
    English to learn whether anything happened.
    """

    ok: bool = True
    detail: str = Field(description='What changed, in one line.')


class TenantInfo(BaseModel):
    """A community the caller can address."""

    model_config = ConfigDict(from_attributes=True)

    slug: str = Field(description="Pass this as the `tenant` argument to other tools.")
    name: str
    roles: List[str] = Field(
        default_factory=list,
        description="Roles the caller holds in this community; empty means none.",
    )
    features: List[str] = Field(
        default_factory=list,
        description=(
            "Optional subsystems this community has switched on. A tool for a "
            "feature absent here reports not_found, so check this before calling."
        ),
    )


class WhoAmI(BaseModel):
    """The caller's identity and reach, for orienting before any other call."""

    user_id: int
    username: str
    display_name: Optional[str] = None
    is_super_admin: bool
    can_write: bool = Field(
        description=(
            "Whether this connection was approved to change data. When false, "
            "only the read tools are served and any write is refused."
        )
    )
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


class TournamentSignupInfo(BaseModel):
    """One tournament as a prospective entrant sees it.

    ``can_sign_up`` / ``can_withdraw`` are the service's own answer, not a
    guess from the window: a model that reasons from ``window`` alone would
    offer a signup the tournament's Challonge link or the caller's existing
    enrolment already rules out.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    window: str
    enrolled: bool
    entrant_count: int
    can_sign_up: bool
    can_withdraw: bool
    signups_open_at: Optional[datetime] = None
    signups_close_at: Optional[datetime] = None


class StageInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_active: bool
    stream_url: Optional[str] = None


class MatchTimeSuggestion(BaseModel):
    """A suggested slot. Wrapped in a model rather than returned as a bare
    datetime so the tool publishes a named output schema."""

    suggested_at: datetime = Field(description='UTC start time for the match.')


class RandomizerInfo(BaseModel):
    """A randomizer this community can actually roll seeds from."""

    randomizer: str
    supports_triforce_texts: bool = False


class TriforceTextEntry(BaseModel):
    id: int
    tournament_id: int
    text: str
    author: Optional[str] = None
    status: str = Field(description='pending, approved, or rejected.')
    submitted_by: Optional[str] = None
    created_at: Optional[datetime] = None


class VolunteerPositionInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    is_active: bool = True
    display_order: int = 0


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


class StageBlock(BaseModel):
    """One stage's slice of a day's schedule."""

    stage: Optional[str] = None
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
    stage: Optional[str] = None
    restream_url: Optional[str] = None


class AvailabilityWindow(BaseModel):
    """One declared window of a player's availability."""

    starts_at: datetime
    ends_at: datetime
    status: str = Field(description='available, preferred, or unavailable.')
    note: Optional[str] = None


class PlayerAvailability(BaseModel):
    user_id: int
    name: Optional[str] = None
    windows: List[AvailabilityWindow] = Field(default_factory=list)


class LoanRecord(BaseModel):
    """One checkout of a piece of equipment; open while `checked_in_at` is null."""

    id: int
    borrower: Optional[str] = None
    checked_out_at: Optional[datetime] = None
    checked_out_by: Optional[str] = None
    checked_in_at: Optional[datetime] = None
    checked_in_by: Optional[str] = None


class EquipmentSummary(BaseModel):
    id: int
    asset_number: int
    name: str
    status: str
    owner: Optional[str] = None
    borrower: Optional[str] = Field(
        default=None, description='Who currently holds it, when it is checked out.'
    )


class EquipmentDetail(EquipmentSummary):
    """An asset plus its checkout history.

    `private_notes` is deliberately absent: the field is staff-only scratch text
    about an asset, and nothing a scheduling question needs.
    """

    description: Optional[str] = None
    loans: List[LoanRecord] = Field(default_factory=list)


class PresetSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    randomizer: str
    description: Optional[str] = None


class PresetDetail(PresetSummary):
    """A preset with its full randomizer settings payload."""

    settings: Optional[object] = None


class RaceRoomInfo(BaseModel):
    """A racetime.gg room Wizzrobe opened for a match."""

    id: int
    slug: str
    category: str
    room_name: Optional[str] = None
    status: str
    match_id: Optional[int] = None
    opened_at: Optional[datetime] = None


class RaceRoomProfileInfo(BaseModel):
    """The room settings a tournament rolls its racetime rooms with."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    goal: Optional[str] = None
    invitational: bool = False
    unlisted: bool = False
    auto_start: bool = True
    streaming_required: bool = False
    time_limit: Optional[int] = Field(
        default=None, description='Hours before the room auto-closes.'
    )


class SpeedGamingLink(BaseModel):
    """A SpeedGaming event whose episodes are pulled into a tournament."""

    id: int
    tournament_id: int
    event_slug: str
    content_type: Optional[str] = None
    active: bool = True
    last_synced_at: Optional[datetime] = None
    last_status: Optional[str] = None
    last_error: Optional[str] = None


class SpeedGamingEpisode(BaseModel):
    """One pulled episode and whether it turned into a match.

    The upstream `payload` is omitted: it is a large nested blob whose useful
    fields are already flattened onto the match this episode produced.
    """

    id: int
    sg_episode_id: str
    title: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    sync_status: str
    synced_at: Optional[datetime] = None
    sync_error: Optional[str] = None


class BracketDetail(BaseModel):
    """One bracket stage and its shape."""

    id: int
    tournament_id: int
    name: str
    format: str
    state: str
    stage_order: int = 0
    entry_count: int = 0


class BracketMatchInfo(BaseModel):
    """One pairing in a bracket, by round and position."""

    id: int
    round: int
    position: int
    group_number: Optional[int] = None
    state: str
    entry1: Optional[str] = None
    entry2: Optional[str] = None
    entry1_score: Optional[int] = None
    entry2_score: Optional[int] = None
    winner: Optional[str] = None
    forfeit: bool = False
    best_of: Optional[int] = None


class BracketEntrantInfo(BaseModel):
    """Someone enrolled in a tournament's brackets."""

    id: int
    display_name: str
    status: str
    user_id: Optional[int] = None


class QualifierPoolInfo(BaseModel):
    id: int
    name: str
    preset: Optional[str] = None
    permalink_count: int = 0


class QualifierDetail(BaseModel):
    """An async qualifier's configuration and its pools."""

    id: int
    name: str
    description: Optional[str] = None
    event_name: Optional[str] = None
    is_active: bool = True
    opens_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None
    runs_per_pool: int = 1
    allowed_reattempts: int = 0
    results_public: bool = False
    pools: List[QualifierPoolInfo] = Field(default_factory=list)


class LeaderboardRow(BaseModel):
    """One entrant's standing in an async qualifier.

    `actual` scores unfilled slots as zero; `estimate` projects them at the
    runner's mean, so a partial entrant is not understated.
    """

    rank: int
    user_id: int
    name: str
    actual: float
    estimate: float
    slots_filled: int
    slots_total: int


class LiveRaceInfo(BaseModel):
    """A scheduled live race that feeds runs into a qualifier pool."""

    id: int
    match_title: str
    status: str
    pool: Optional[str] = None
    racetime_slug: Optional[str] = None


class ServiceHealthProbe(BaseModel):
    """The latest outcome of one dependency probe."""

    key: str
    label: str
    category: str
    status: str
    message: str
    checked_at: datetime


class WebhookInfo(BaseModel):
    """An outbound webhook. The signing secret is never returned."""

    id: int
    name: str
    url: str
    event_types: List[str] = Field(default_factory=list)
    is_active: bool = True


class WebhookDeliveryInfo(BaseModel):
    """One delivery attempt. The serialized payload is omitted as bulk."""

    id: int
    event_type: str
    success: bool
    response_status: Optional[int] = None
    attempt_count: int = 0
    error: Optional[str] = None
    created_at: datetime
    delivered_at: Optional[datetime] = None


class FeedbackEntry(BaseModel):
    """One piece of user-submitted feedback."""

    id: int
    category: str
    status: str
    message: str
    page_url: Optional[str] = None
    submitted_by: Optional[str] = None
    created_at: datetime


# StageBlock forward-references MatchSummary, which is declared after it.
StageBlock.model_rebuild()
