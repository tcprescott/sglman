"""Tortoise ORM models for Wizzrobe.

Historically a single ``models.py``; split into cohesive per-domain submodules
once it outgrew the file-length budget. Every model and enum is re-exported here
so ``from models import X`` keeps working and Tortoise/aerich still discover the
whole schema through the app's single ``"models"`` entry (discovery iterates this
package's namespace). Cross-model foreign keys use string references
(``'models.User'``), so submodules have no import-order dependencies on each
other — only the shared enums in :mod:`models.enums` are imported directly.
"""

from .async_qualifier import (
    AsyncQualifier,
    AsyncQualifierLiveRace,
    AsyncQualifierPermalink,
    AsyncQualifierPool,
    AsyncQualifierReviewNote,
    AsyncQualifierRun,
)
from .audit import AuditLog, TelemetryEvent
from .bracket import (
    Bracket,
    BracketEntrant,
    BracketEntry,
    BracketMatch,
    BracketMatchGame,
)
from .challonge import (
    ChallongeApiUsage,
    ChallongeConnection,
    ChallongeMatch,
    ChallongeParticipant,
)
from .column_guards import FieldValueError, install_column_guards
from .discord_events import DiscordScheduledEvent
from .enums import (
    STATION_REGEXES,
    SYSTEM_USER_DISCORD_ID,
    ApiTokenOrigin,
    AsyncQualifierLiveRaceStatus,
    AsyncQualifierReviewStatus,
    AsyncQualifierRunStatus,
    BotStatus,
    BracketEntrantStatus,
    BracketEntryStatus,
    BracketFormat,
    BracketMatchGameState,
    BracketMatchState,
    BracketState,
    ChallongeMatchState,
    DiscordEventSource,
    EquipmentStatus,
    FeatureFlag,
    FeedbackCategory,
    FeedbackStatus,
    JoinRequestStatus,
    MatchNotificationLevel,
    RaceRoomStatus,
    Role,
    RoleSource,
    StationFormat,
    SyncStatus,
    VolunteerAvailabilityStatus,
)
from .equipment import Equipment, EquipmentLoan
from .feature_flag import FeatureFlagGroup, TenantFeatureFlag
from .feedback import Feedback
from .match import (
    Commentator,
    Match,
    MatchAcknowledgment,
    MatchPlayers,
    MatchWatcher,
    Station,
    StreamRoom,
    Tracker,
)
from .mcp import McpAuthorizationCode, McpOAuthClient
from .preferences import UserTablePreference
from .racetime import RaceRoomProfile, RacetimeBot, RacetimeBotTenant, RacetimeRoom
from .speedgaming import SpeedGamingEpisode, SpeedGamingEventLink
from .system import SystemConfiguration
from .tenant import Tenant, TenantJoinRequest, TenantMembership
from .tournament import (
    GeneratedSeeds,
    Preset,
    RandomizerCredential,
    Tournament,
    TournamentNotificationPreference,
    TournamentPlayers,
    TriforceText,
)
from .user import ApiToken, DiscordRoleMapping, User, UserRole, WebPushSubscription
from .volunteer import (
    PlayerAvailability,
    VolunteerAssignment,
    VolunteerAvailability,
    VolunteerPosition,
    VolunteerProfile,
    VolunteerQualification,
    VolunteerShift,
)
from .webhook import Webhook, WebhookDelivery

# Every model is imported by now, so the column-fit guards can be attached to
# their fields. Must stay last: it walks this module's namespace for models.
install_column_guards(globals())

__all__ = [
    'STATION_REGEXES',
    # constants
    'SYSTEM_USER_DISCORD_ID',
    # user / auth
    'ApiToken',
    # enums
    'ApiTokenOrigin',
    # async qualifier
    'AsyncQualifier',
    'AsyncQualifierLiveRace',
    'AsyncQualifierLiveRaceStatus',
    'AsyncQualifierPermalink',
    'AsyncQualifierPool',
    'AsyncQualifierReviewNote',
    'AsyncQualifierReviewStatus',
    'AsyncQualifierRun',
    'AsyncQualifierRunStatus',
    # audit / telemetry
    'AuditLog',
    'BotStatus',
    # brackets
    'Bracket',
    'BracketEntrant',
    'BracketEntrantStatus',
    'BracketEntry',
    'BracketEntryStatus',
    'BracketFormat',
    'BracketMatch',
    'BracketMatchGame',
    'BracketMatchGameState',
    'BracketMatchState',
    'BracketState',
    # challonge
    'ChallongeApiUsage',
    'ChallongeConnection',
    'ChallongeMatch',
    'ChallongeMatchState',
    'ChallongeParticipant',
    # match / crew
    'Commentator',
    'DiscordEventSource',
    'DiscordRoleMapping',
    # discord events
    'DiscordScheduledEvent',
    # equipment
    'Equipment',
    'EquipmentLoan',
    'EquipmentStatus',
    'FeatureFlag',
    'FeatureFlagGroup',
    # feedback
    'Feedback',
    'FeedbackCategory',
    'FeedbackStatus',
    # column guards
    'FieldValueError',
    # tournament
    'GeneratedSeeds',
    'JoinRequestStatus',
    'Match',
    'MatchAcknowledgment',
    'MatchNotificationLevel',
    'MatchPlayers',
    'MatchWatcher',
    # mcp oauth
    'McpAuthorizationCode',
    'McpOAuthClient',
    # volunteer
    'PlayerAvailability',
    'Preset',
    # racetime
    'RaceRoomProfile',
    'RaceRoomStatus',
    'RacetimeBot',
    'RacetimeBotTenant',
    'RacetimeRoom',
    'RandomizerCredential',
    'Role',
    'RoleSource',
    # speedgaming
    'SpeedGamingEpisode',
    'SpeedGamingEventLink',
    'Station',
    'StationFormat',
    'StreamRoom',
    'SyncStatus',
    # system
    'SystemConfiguration',
    'TelemetryEvent',
    # tenant
    'Tenant',
    'TenantFeatureFlag',
    'TenantJoinRequest',
    'TenantMembership',
    'Tournament',
    'TournamentNotificationPreference',
    'TournamentPlayers',
    'Tracker',
    'TriforceText',
    'User',
    'UserRole',
    # per-user UI preferences
    'UserTablePreference',
    'VolunteerAssignment',
    'VolunteerAvailability',
    'VolunteerAvailabilityStatus',
    'VolunteerPosition',
    'VolunteerProfile',
    'VolunteerQualification',
    'VolunteerShift',
    'WebPushSubscription',
    # webhooks
    'Webhook',
    'WebhookDelivery',
]
