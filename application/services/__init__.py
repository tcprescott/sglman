"""
Service Layer - Business Logic

Services orchestrate business operations, validate data, and coordinate
between repositories. They should NOT know about UI components.
"""

from application.errors import NotFoundError, require_found

from .analytics_service import AnalyticsService
from .api_token_service import ApiTokenService
from .async_qualifier import (
    AsyncQualifierConfig,
    AsyncQualifierDraw,
    AsyncQualifierLiveRaceService,
    AsyncQualifierService,
    async_qualifier_access,
    async_qualifier_scoring,
    validate_async_qualifier_config,
    validate_counts,
    validate_window,
)
from .audit_service import AuditService
from .auth_service import AuthService, get_user_from_discord_id
from .bracket_config import BracketConfig, validate_bracket_config
from .bracket_service import BracketService
from .challonge_service import ChallongeService
from .crew_service import CrewService
from .discord import (
    DiscordEventReconcilerService,
    DiscordEventSyncService,
    DiscordLinkService,
    DiscordRoleMappingService,
    DiscordService,
    discord_event_worker,
    discord_queue,
)
from .volunteer import (
    DraftPolicy,
    VolunteerAutoscheduleService,
    VolunteerAvailabilityService,
    VolunteerExportService,
    VolunteerPositionService,
    VolunteerProfileService,
    VolunteerQualificationService,
    VolunteerScheduleService,
    volunteer_reminder,
)
from .service_health_service import ProbeResult, ServiceHealthService, ServiceStatus
from . import service_health_worker
from .equipment_service import EquipmentService
from .feature_flag_service import FeatureFlagService
from .feedback_service import FeedbackService
from .identity_link_service import IdentityLinkProvider, IdentityLinkService
from .match import (
    CancellationMixin,
    MatchDisplayService,
    MatchParticipants,
    MatchScheduleService,
    MatchService,
    MatchSuggestionService,
    MatchWatcherService,
    assert_sg_fields_unchanged,
)
from . import availability_windows
from .mcp_auth_service import McpAuthService
from .player_availability_service import PlayerAvailabilityService
from . import oauth_handoff_service
from .preset_service import PresetService
from .randomizer_credential_service import RandomizerCredentialService
from .race_room_profile_service import RaceRoomProfileService
from .race_room_service import RaceRoomService
from . import race_room_worker
from .racetime_bot_service import RacetimeBotService
from .racetime_room_service import RacetimeRoomService
from .racetime_service import RacetimeService
from . import reporting_shared
from .reports_service import ReportsService
from .seedgen_service import SeedGenerationService
from .speedgaming_etl_service import SpeedGamingETLService
from .speedgaming_sync_service import SpeedGamingSyncService
from . import speedgaming_sync_worker
from .station_service import StationService
from .stream_room_service import StreamRoomService
from .system_config_service import SystemConfigService
from .tenant_service import TenantService
from .tenant_theme_service import TenantThemeService
from .telemetry_service import TelemetryService
from .tournament_notification_service import TournamentNotificationService
from .tournament_service import TournamentService
from .triforce_text_service import TriforceTextService
from .twitch_service import TwitchService
from .user_service import UserService
from .tournament_config import TournamentConfig, validate_tournament_config
from .web_push_service import WebPushService
from .webhook_service import WebhookService

__all__ = [
    'NotFoundError',
    'require_found',
    'TournamentConfig',
    'validate_tournament_config',
    'AnalyticsService',
    'ApiTokenService',
    'AsyncQualifierConfig',
    'validate_async_qualifier_config',
    'async_qualifier_access',
    'async_qualifier_scoring',
    'availability_windows',
    'reporting_shared',
    'AsyncQualifierDraw',
    'AsyncQualifierService',
    'AsyncQualifierLiveRaceService',
    'validate_counts',
    'validate_window',
    'AuditService',
    'AuthService',
    'BracketConfig',
    'validate_bracket_config',
    'BracketService',
    'ChallongeService',
    'CrewService',
    'discord_queue',
    'get_user_from_discord_id',
    'volunteer_reminder',
    'DiscordEventReconcilerService',
    'ServiceHealthService',
    'ServiceStatus',
    'ProbeResult',
    'service_health_worker',
    'DiscordEventSyncService',
    'discord_event_worker',
    'DiscordLinkService',
    'DiscordRoleMappingService',
    'DiscordService',
    'EquipmentService',
    'FeatureFlagService',
    'FeedbackService',
    'IdentityLinkProvider',
    'IdentityLinkService',
    'CancellationMixin',
    'MatchParticipants',
    'MatchService',
    'assert_sg_fields_unchanged',
    'MatchDisplayService',
    'MatchScheduleService',
    'MatchSuggestionService',
    'MatchWatcherService',
    'McpAuthService',
    'oauth_handoff_service',
    'PlayerAvailabilityService',
    'PresetService',
    'RandomizerCredentialService',
    'RaceRoomProfileService',
    'RaceRoomService',
    'race_room_worker',
    'RacetimeBotService',
    'RacetimeRoomService',
    'RacetimeService',
    'ReportsService',
    'SeedGenerationService',
    'SpeedGamingETLService',
    'SpeedGamingSyncService',
    'speedgaming_sync_worker',
    'StationService',
    'StreamRoomService',
    'SystemConfigService',
    'TenantService',
    'TenantThemeService',
    'TelemetryService',
    'TournamentNotificationService',
    'TournamentService',
    'TriforceTextService',
    'TwitchService',
    'UserService',
    'DraftPolicy',
    'VolunteerAutoscheduleService',
    'VolunteerAvailabilityService',
    'VolunteerExportService',
    'VolunteerQualificationService',
    'VolunteerPositionService',
    'VolunteerProfileService',
    'VolunteerScheduleService',
    'WebPushService',
    'WebhookService',
]
