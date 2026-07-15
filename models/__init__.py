"""Tortoise ORM models for SGL On Site.

Historically a single ``models.py``; split into cohesive per-domain submodules
once it outgrew the file-length budget. Every model and enum is re-exported here
so ``from models import X`` keeps working and Tortoise/aerich still discover the
whole schema through the app's single ``"models"`` entry (discovery iterates this
package's namespace). Cross-model foreign keys use string references
(``'models.User'``), so submodules have no import-order dependencies on each
other — only the shared enums in :mod:`models.enums` are imported directly.
"""

from .enums import (
    SYSTEM_USER_DISCORD_ID,
    AsyncQualifierLiveRaceStatus,
    AsyncQualifierReviewStatus,
    AsyncQualifierRunStatus,
    BotStatus,
    ChallongeMatchState,
    DiscordEventSource,
    EquipmentStatus,
    FeatureFlag,
    FeedbackCategory,
    FeedbackStatus,
    MatchNotificationLevel,
    RaceRoomStatus,
    Role,
    RoleSource,
    StationFormat,
    SyncStatus,
    VolunteerAvailabilityStatus,
)
from .tenant import Tenant, TenantMembership
from .feature_flag import TenantFeatureFlag
from .user import ApiToken, DiscordRoleMapping, User, UserRole, WebPushSubscription
from .tournament import (
    GeneratedSeeds,
    Preset,
    Tournament,
    TournamentNotificationPreference,
    TournamentPlayers,
    TriforceText,
)
from .match import (
    Commentator,
    Match,
    MatchAcknowledgment,
    MatchPlayers,
    MatchWatcher,
    StreamRoom,
    Tracker,
)
from .equipment import Equipment, EquipmentLoan
from .feedback import Feedback
from .volunteer import (
    PlayerAvailability,
    VolunteerAssignment,
    VolunteerAvailability,
    VolunteerPosition,
    VolunteerProfile,
    VolunteerQualification,
    VolunteerShift,
)
from .audit import AuditLog, TelemetryEvent
from .system import SystemConfiguration
from .webhook import Webhook, WebhookDelivery
from .challonge import (
    ChallongeApiUsage,
    ChallongeConnection,
    ChallongeMatch,
    ChallongeParticipant,
)
from .racetime import RaceRoomProfile, RacetimeBot, RacetimeBotTenant, RacetimeRoom
from .speedgaming import SpeedGamingEpisode, SpeedGamingEventLink
from .discord_events import DiscordScheduledEvent
from .async_qualifier import (
    AsyncQualifier,
    AsyncQualifierLiveRace,
    AsyncQualifierPermalink,
    AsyncQualifierPool,
    AsyncQualifierReviewNote,
    AsyncQualifierRun,
)

__all__ = [
    # constants
    'SYSTEM_USER_DISCORD_ID',
    # enums
    'AsyncQualifierLiveRaceStatus',
    'AsyncQualifierReviewStatus',
    'AsyncQualifierRunStatus',
    'BotStatus',
    'ChallongeMatchState',
    'DiscordEventSource',
    'EquipmentStatus',
    'FeatureFlag',
    'FeedbackCategory',
    'FeedbackStatus',
    'MatchNotificationLevel',
    'RaceRoomStatus',
    'Role',
    'RoleSource',
    'StationFormat',
    'SyncStatus',
    'VolunteerAvailabilityStatus',
    # tenant
    'Tenant',
    'TenantMembership',
    'TenantFeatureFlag',
    # user / auth
    'ApiToken',
    'DiscordRoleMapping',
    'User',
    'UserRole',
    'WebPushSubscription',
    # tournament
    'GeneratedSeeds',
    'Preset',
    'Tournament',
    'TournamentNotificationPreference',
    'TournamentPlayers',
    'TriforceText',
    # match / crew
    'Commentator',
    'Match',
    'MatchAcknowledgment',
    'MatchPlayers',
    'MatchWatcher',
    'StreamRoom',
    'Tracker',
    # equipment
    'Equipment',
    'EquipmentLoan',
    # feedback
    'Feedback',
    # volunteer
    'PlayerAvailability',
    'VolunteerAssignment',
    'VolunteerAvailability',
    'VolunteerPosition',
    'VolunteerProfile',
    'VolunteerQualification',
    'VolunteerShift',
    # audit / telemetry
    'AuditLog',
    'TelemetryEvent',
    # system
    'SystemConfiguration',
    # webhooks
    'Webhook',
    'WebhookDelivery',
    # challonge
    'ChallongeApiUsage',
    'ChallongeConnection',
    'ChallongeMatch',
    'ChallongeParticipant',
    # racetime
    'RaceRoomProfile',
    'RacetimeBot',
    'RacetimeBotTenant',
    'RacetimeRoom',
    # speedgaming
    'SpeedGamingEpisode',
    'SpeedGamingEventLink',
    # discord events
    'DiscordScheduledEvent',
    # async qualifier
    'AsyncQualifier',
    'AsyncQualifierLiveRace',
    'AsyncQualifierPermalink',
    'AsyncQualifierPool',
    'AsyncQualifierReviewNote',
    'AsyncQualifierRun',
]
