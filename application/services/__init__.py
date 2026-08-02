"""
Service Layer - Business Logic

Services orchestrate business operations, validate data, and coordinate
between repositories. They should NOT know about UI components.
"""

from application.errors import NotFoundError, require_found

from . import (
    availability_windows,
    notification_links,
    oauth_handoff_service,
    race_room_worker,
    reporting_shared,
    service_health_worker,
    speedgaming_sync_worker,
)
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
from .equipment_service import EquipmentService
from .event_info_service import EventInfoService
from .feature_flag_service import FeatureFlagService
from .feedback_service import FeedbackService
from .help_service import HelpService
from .identity_link_service import IdentityLinkProvider, IdentityLinkService
from .match import (
    CancellationMixin,
    MatchDisplayService,
    MatchParticipants,
    MatchScheduleService,
    MatchService,
    MatchStreamVolunteerService,
    MatchSuggestionService,
    MatchWatcherService,
    assert_sg_fields_unchanged,
)
from .mcp_auth_service import McpAuthService
from .player_availability_service import PlayerAvailabilityService
from .preset_service import PresetService
from .race_room_profile_service import RaceRoomProfileService
from .race_room_service import RaceRoomService
from .racetime_bot_service import RacetimeBotService
from .racetime_room_service import RacetimeRoomService
from .racetime_service import RacetimeService
from .randomizer_credential_service import RandomizerCredentialService
from .reports_service import ReportsService
from .seedgen_service import SeedGenerationService
from .service_health_service import ProbeResult, ServiceHealthService, ServiceStatus
from .speedgaming_etl_service import SpeedGamingETLService
from .speedgaming_sync_service import SpeedGamingSyncService
from .stage_service import StageService
from .station_service import StationService
from .system_config_service import SystemConfigService
from .table_preference_service import TablePreferenceService
from .telemetry_service import TelemetryService
from .tenant_membership_service import TenantMembershipService
from .tenant_service import TenantService
from .tenant_setup_service import SetupStep, TenantSetupService
from .tenant_theme_service import TenantThemeService
from .timezone_service import TimezoneService
from .tournament_config import TournamentConfig, validate_tournament_config
from .tournament_notification_service import TournamentNotificationService
from .tournament_service import TournamentService
from .triforce_text_service import TriforceTextService
from .twitch_service import TwitchService
from .user_service import UserService
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
from .web_push_service import WebPushService
from .webhook_service import WebhookService

__all__ = [
    'AnalyticsService',
    'ApiTokenService',
    'AsyncQualifierConfig',
    'AsyncQualifierDraw',
    'AsyncQualifierLiveRaceService',
    'AsyncQualifierService',
    'AuditService',
    'AuthService',
    'BracketConfig',
    'BracketService',
    'CancellationMixin',
    'ChallongeService',
    'CrewService',
    'DiscordEventReconcilerService',
    'DiscordEventSyncService',
    'DiscordLinkService',
    'DiscordRoleMappingService',
    'DiscordService',
    'DraftPolicy',
    'EquipmentService',
    'EventInfoService',
    'FeatureFlagService',
    'FeedbackService',
    'HelpService',
    'IdentityLinkProvider',
    'IdentityLinkService',
    'MatchDisplayService',
    'MatchParticipants',
    'MatchScheduleService',
    'MatchService',
    'MatchStreamVolunteerService',
    'MatchSuggestionService',
    'MatchWatcherService',
    'McpAuthService',
    'NotFoundError',
    'PlayerAvailabilityService',
    'PresetService',
    'ProbeResult',
    'RaceRoomProfileService',
    'RaceRoomService',
    'RacetimeBotService',
    'RacetimeRoomService',
    'RacetimeService',
    'RandomizerCredentialService',
    'ReportsService',
    'SeedGenerationService',
    'ServiceHealthService',
    'ServiceStatus',
    'SetupStep',
    'SpeedGamingETLService',
    'SpeedGamingSyncService',
    'StageService',
    'StationService',
    'SystemConfigService',
    'TablePreferenceService',
    'TelemetryService',
    'TenantMembershipService',
    'TenantService',
    'TenantSetupService',
    'TenantThemeService',
    'TimezoneService',
    'TournamentConfig',
    'TournamentNotificationService',
    'TournamentService',
    'TriforceTextService',
    'TwitchService',
    'UserService',
    'VolunteerAutoscheduleService',
    'VolunteerAvailabilityService',
    'VolunteerExportService',
    'VolunteerPositionService',
    'VolunteerProfileService',
    'VolunteerQualificationService',
    'VolunteerScheduleService',
    'WebPushService',
    'WebhookService',
    'assert_sg_fields_unchanged',
    'async_qualifier_access',
    'async_qualifier_scoring',
    'availability_windows',
    'discord_event_worker',
    'discord_queue',
    'get_user_from_discord_id',
    'notification_links',
    'oauth_handoff_service',
    'race_room_worker',
    'reporting_shared',
    'require_found',
    'service_health_worker',
    'speedgaming_sync_worker',
    'validate_async_qualifier_config',
    'validate_bracket_config',
    'validate_counts',
    'validate_tournament_config',
    'validate_window',
    'volunteer_reminder',
]
