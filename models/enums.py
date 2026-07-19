from enum import Enum


class Role(str, Enum):
    STAFF = 'staff'
    PROCTOR = 'proctor'
    STREAM_MANAGER = 'stream_manager'
    TRIFORCE_SUBMITTER = 'triforce_submitter'
    VOLUNTEER_COORDINATOR = 'volunteer_coordinator'
    EQUIPMENT_MANAGER = 'equipment_manager'
    VOLUNTEER = 'volunteer'
    # Online-tournament admin surfaces (see docs/online-tournaments). Each gates a
    # new subsystem's management UI/worker actions the way STAFF does the rest.
    PRESET_MANAGER = 'preset_manager'
    SYNC_ADMIN = 'sync_admin'
    QUALIFIER_ADMIN = 'qualifier_admin'
    # Global platform role: manages tenants on the /platform surface. Its
    # UserRole rows carry tenant=NULL (the only role that may) and stay visible
    # inside any tenant request. Not grantable per-tenant.
    SUPER_ADMIN = 'super_admin'


# Sentinel ``discord_id`` for the reserved system :class:`User` that automation
# (workers, racetime/Discord bot handlers, ETL, qualifier scoring) acts as. A
# real snowflake is always a large positive integer, so ``0`` can never collide
# with a genuine Discord account. The row is marked ``is_system`` and resolved
# via ``UserService.get_system_user()``.
SYSTEM_USER_DISCORD_ID = 0


class FeatureFlag(str, Enum):
    """Per-tenant feature flags — one member per deliberately-gated subsystem.

    A flag exists ONLY when a feature is intentionally gated; this is not a
    per-feature switch for the whole app. Flags default OFF and are governed
    two-tier (super-admin availability + tenant enable). The human copy and
    grouping for each flag live in :mod:`application.feature_flags`.

    ``(str, Enum)`` — the ``.value`` is the stable key persisted on
    ``TenantFeatureFlag.flag``, so renaming a value is a data migration.
    """

    ASYNC_QUALIFIERS = 'async_qualifiers'
    RACETIME_ROOMS = 'racetime_rooms'
    SPEEDGAMING_ETL = 'speedgaming_etl'
    DK64_RANDOMIZER = 'dk64_randomizer'
    CHALLONGE = 'challonge'
    EQUIPMENT = 'equipment'
    VOLUNTEERS = 'volunteers'
    TRIFORCE_TEXTS = 'triforce_texts'


class RoleSource(str, Enum):
    MANUAL = 'manual'
    DISCORD = 'discord'


class VolunteerAvailabilityStatus(str, Enum):
    AVAILABLE = 'available'
    UNAVAILABLE = 'unavailable'
    PREFERRED = 'preferred'


class FeedbackCategory(str, Enum):
    BUG = 'bug'
    SUGGESTION = 'suggestion'
    PRAISE = 'praise'
    OTHER = 'other'


class FeedbackStatus(str, Enum):
    NEW = 'new'
    REVIEWED = 'reviewed'


class EquipmentStatus(str, Enum):
    AVAILABLE = 'available'
    CHECKED_OUT = 'checked_out'
    RETIRED = 'retired'


class StationFormat(str, Enum):
    FREE = 'free'
    NUMERIC = 'numeric'
    STRUCTURED = 'structured'
    ALPHANUMERIC = 'alphanumeric'


class MatchNotificationLevel(str, Enum):
    NONE = 'none'
    STREAMED = 'streamed'
    STREAMED_AND_CANDIDATES = 'streamed_and_candidates'
    ALL = 'all'


class ChallongeMatchState(str, Enum):
    """Mirrors Challonge's match states relevant to scheduling."""

    PENDING = 'pending'   # participants not yet fully determined
    OPEN = 'open'         # both participants known and ready to play
    COMPLETE = 'complete' # result recorded on Challonge


class BotStatus(str, Enum):
    """Health of a racetime bot's websocket connection.

    The values are *written* by the PR 4 runtime (heartbeat/connect/error) and
    read by the platform health surface; in this PR the column exists but stays
    at its ``UNKNOWN`` default.
    """

    UNKNOWN = 'unknown'
    CONNECTED = 'connected'
    DISCONNECTED = 'disconnected'
    ERROR = 'error'


class RaceRoomStatus(str, Enum):
    """Cached racetime room lifecycle state (written by PR 4/6)."""

    OPEN = 'open'
    IN_PROGRESS = 'in_progress'
    FINISHED = 'finished'
    CANCELLED = 'cancelled'


class SyncStatus(str, Enum):
    """Reconciliation state of a synced SpeedGaming episode (PR 7).

    ``(str, Enum)`` (not ``StrEnum``) — render ``.value`` in f-strings, never the
    bare member (which repr's as ``SyncStatus.SYNCED``).
    """

    PENDING = 'pending'      # discovered upstream, not yet materialized
    SYNCED = 'synced'        # materialized/refreshed into a Match this cycle
    SKIPPED = 'skipped'      # a lifecycle guard held the refresh back
    CANCELLED = 'cancelled'  # upstream episode gone; the Match soft-detached
    ERROR = 'error'          # transform/load failed (see ``sync_error``)


class DiscordEventSource(str, Enum):
    """What Wizzrobe schedule row a mirrored Discord event came from (PR 8).

    The ``DiscordScheduledEvent`` link is polymorphic: ``(source_type, source_id)``
    identifies the Wizzrobe row a Discord Scheduled Event mirrors. Today only
    ``MATCH`` is materialized (native + SG-imported matches both live in ``Match``);
    qualifier windows / live races join later without a schema change.

    ``(str, Enum)`` (not ``StrEnum``) — render ``.value`` in f-strings.
    """

    MATCH = 'match'


class AsyncQualifierRunStatus(str, Enum):
    """Execution state of a single async-qualifier run (PR 9).

    ``(str, Enum)`` (not ``StrEnum``) — render ``.value`` in f-strings, never the
    bare member (which repr's as ``AsyncQualifierRunStatus.FINISHED``).

    Web-first collapses reveal and start, so a run is created ``IN_PROGRESS`` the
    moment a player draws (the permalink is revealed then). ``PENDING`` is
    reserved for a run pre-created before a synchronous start — the live-race path
    (PR 10) — and is unused by the self-paced core flow.
    """

    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    FINISHED = 'finished'
    FORFEIT = 'forfeit'
    DISQUALIFIED = 'disqualified'


class AsyncQualifierReviewStatus(str, Enum):
    """Review state of a finished async-qualifier run (PR 9)."""

    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'


class AsyncQualifierLiveRaceStatus(str, Enum):
    """Lifecycle of a synchronous racetime qualifier race (PR 10).

    ``(str, Enum)`` (not ``StrEnum``) — render ``.value`` in f-strings, never the
    bare member (which repr's as ``AsyncQualifierLiveRaceStatus.FINISHED``).

    ``SCHEDULED`` before a room opens, ``PENDING`` once a room exists but the race
    has not started, ``IN_PROGRESS`` while racing, ``FINISHED`` once the entrants'
    results are captured into runs.
    """

    SCHEDULED = 'scheduled'
    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    FINISHED = 'finished'
