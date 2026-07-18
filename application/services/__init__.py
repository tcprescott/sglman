"""
Service Layer - Business Logic

Services orchestrate business operations, validate data, and coordinate
between repositories. They should NOT know about UI components.
"""

from application.errors import NotFoundError, require_found

from .analytics_service import AnalyticsService
from .api_token_service import ApiTokenService
from .async_qualifier_config import (
    AsyncQualifierConfig,
    validate_async_qualifier_config,
)
from . import async_qualifier_access
from . import async_qualifier_scoring
from .async_qualifier_draw import AsyncQualifierDraw
from .async_qualifier_live_race_service import AsyncQualifierLiveRaceService
from .async_qualifier_rules import validate_counts, validate_window
from .async_qualifier_service import AsyncQualifierService
from .audit_service import AuditService
from .auth_service import AuthService, get_user_from_discord_id
from .challonge_service import ChallongeService
from .crew_service import CrewService
from . import discord_queue
from . import volunteer_reminder
from .discord_event_reconciler_service import DiscordEventReconcilerService
from .discord_event_sync_service import DiscordEventSyncService
from . import discord_event_worker
from .discord_link_service import DiscordLinkService
from .service_health_service import ProbeResult, ServiceHealthService, ServiceStatus
from . import service_health_worker
from .discord_role_mapping_service import DiscordRoleMappingService
from .discord_service import DiscordService
from .equipment_service import EquipmentService
from .feature_flag_service import FeatureFlagService
from .feedback_service import FeedbackService
from .identity_link_service import IdentityLinkProvider, IdentityLinkService
from .match_participants import MatchParticipants
from .match_service import MatchService
from .match_source_guard import assert_sg_fields_unchanged
from .match_display_service import MatchDisplayService
from .match_schedule_service import MatchScheduleService
from .match_suggestion_service import MatchSuggestionService
from . import availability_windows
from .player_availability_service import PlayerAvailabilityService
from .match_watcher_service import MatchWatcherService
from . import oauth_handoff_service
from .preset_service import PresetService
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
from .stream_room_service import StreamRoomService
from .system_config_service import SystemConfigService
from .tenant_service import TenantService
from .telemetry_service import TelemetryService
from .tournament_notification_service import TournamentNotificationService
from .tournament_service import TournamentService
from .triforce_text_service import TriforceTextService
from .twitch_service import TwitchService
from .user_service import UserService
from .volunteer_autoschedule_service import VolunteerAutoscheduleService
from .volunteer_qualification_service import VolunteerQualificationService
from .volunteer_availability_service import VolunteerAvailabilityService
from .volunteer_position_service import VolunteerPositionService
from .volunteer_profile_service import VolunteerProfileService
from .volunteer_schedule_service import VolunteerScheduleService
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
    'MatchParticipants',
    'MatchService',
    'assert_sg_fields_unchanged',
    'MatchDisplayService',
    'MatchScheduleService',
    'MatchSuggestionService',
    'MatchWatcherService',
    'oauth_handoff_service',
    'PlayerAvailabilityService',
    'PresetService',
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
    'StreamRoomService',
    'SystemConfigService',
    'TenantService',
    'TelemetryService',
    'TournamentNotificationService',
    'TournamentService',
    'TriforceTextService',
    'TwitchService',
    'UserService',
    'VolunteerAutoscheduleService',
    'VolunteerAvailabilityService',
    'VolunteerQualificationService',
    'VolunteerPositionService',
    'VolunteerProfileService',
    'VolunteerScheduleService',
    'WebPushService',
    'WebhookService',
]
