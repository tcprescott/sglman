"""
Data Access Layer (Repository Pattern)

Repositories handle all database queries and return domain objects.
They should NOT contain business logic - only data fetching/persistence.
"""

from .api_token_repository import ApiTokenRepository
from .async_qualifier_repository import (
    AsyncQualifierLiveRaceRepository,
    AsyncQualifierPermalinkRepository,
    AsyncQualifierPoolRepository,
    AsyncQualifierRepository,
    AsyncQualifierReviewNoteRepository,
    AsyncQualifierRunRepository,
)
from .audit_repository import AuditRepository
from .bracket_repository import BracketRepository
from .challonge_repository import ChallongeRepository
from .commentator_repository import CommentatorRepository
from .discord_role_mapping_repository import DiscordRoleMappingRepository
from .discord_scheduled_event_repository import DiscordScheduledEventRepository
from .discord_tournament_grant_repository import DiscordTournamentGrantRepository
from .equipment_repository import EquipmentRepository
from .feature_flag_group_repository import FeatureFlagGroupRepository
from .feature_flag_repository import TenantFeatureFlagRepository
from .feedback_repository import FeedbackRepository
from .match_acknowledgment_repository import MatchAcknowledgmentRepository
from .match_repository import MatchRepository
from .match_stream_volunteer_repository import MatchStreamVolunteerRepository
from .match_watcher_repository import MatchWatcherRepository
from .mcp_auth_repository import McpAuthRepository
from .player_availability_repository import PlayerAvailabilityRepository
from .preset_repository import PresetRepository
from .provider_task_repository import ProviderTaskRepository
from .race_room_profile_repository import RaceRoomProfileRepository
from .racetime_bot_repository import RacetimeBotRepository
from .racetime_room_repository import RacetimeRoomRepository
from .randomizer_credential_repository import RandomizerCredentialRepository
from .reschedule_request_repository import RescheduleRequestRepository
from .speedgaming_episode_repository import SpeedGamingEpisodeRepository
from .speedgaming_event_link_repository import SpeedGamingEventLinkRepository
from .stage_repository import StageRepository
from .station_repository import StationRepository
from .table_preference_repository import TablePreferenceRepository
from .telemetry_repository import TelemetryRepository
from .tenant_join_request_repository import TenantJoinRequestRepository
from .tenant_membership_repository import TenantMembershipRepository
from .tenant_repository import TenantRepository
from .tournament_notification_repository import TournamentNotificationRepository
from .tournament_repository import TournamentRepository
from .tracker_repository import TrackerRepository
from .triforce_text_repository import TriforceTextRepository
from .user_repository import UserRepository
from .user_role_repository import UserRoleRepository
from .volunteer_assignment_repository import VolunteerAssignmentRepository
from .volunteer_availability_repository import VolunteerAvailabilityRepository
from .volunteer_position_repository import VolunteerPositionRepository
from .volunteer_profile_repository import VolunteerProfileRepository
from .volunteer_qualification_repository import VolunteerQualificationRepository
from .volunteer_shift_repository import VolunteerShiftRepository
from .web_push_repository import WebPushRepository
from .webhook_delivery_repository import WebhookDeliveryRepository
from .webhook_repository import WebhookRepository

__all__ = [
    'ApiTokenRepository',
    'AsyncQualifierLiveRaceRepository',
    'AsyncQualifierPermalinkRepository',
    'AsyncQualifierPoolRepository',
    'AsyncQualifierRepository',
    'AsyncQualifierReviewNoteRepository',
    'AsyncQualifierRunRepository',
    'AuditRepository',
    'BracketRepository',
    'ChallongeRepository',
    'CommentatorRepository',
    'DiscordRoleMappingRepository',
    'DiscordScheduledEventRepository',
    'DiscordTournamentGrantRepository',
    'EquipmentRepository',
    'FeatureFlagGroupRepository',
    'FeedbackRepository',
    'MatchAcknowledgmentRepository',
    'MatchRepository',
    'MatchStreamVolunteerRepository',
    'MatchWatcherRepository',
    'McpAuthRepository',
    'PlayerAvailabilityRepository',
    'PresetRepository',
    'ProviderTaskRepository',
    'RaceRoomProfileRepository',
    'RacetimeBotRepository',
    'RacetimeRoomRepository',
    'RandomizerCredentialRepository',
    'RescheduleRequestRepository',
    'SpeedGamingEpisodeRepository',
    'SpeedGamingEventLinkRepository',
    'StageRepository',
    'StationRepository',
    'TablePreferenceRepository',
    'TelemetryRepository',
    'TenantFeatureFlagRepository',
    'TenantJoinRequestRepository',
    'TenantMembershipRepository',
    'TenantRepository',
    'TournamentNotificationRepository',
    'TournamentRepository',
    'TrackerRepository',
    'TriforceTextRepository',
    'UserRepository',
    'UserRoleRepository',
    'VolunteerAssignmentRepository',
    'VolunteerAvailabilityRepository',
    'VolunteerPositionRepository',
    'VolunteerProfileRepository',
    'VolunteerQualificationRepository',
    'VolunteerShiftRepository',
    'WebPushRepository',
    'WebhookDeliveryRepository',
    'WebhookRepository',
]
