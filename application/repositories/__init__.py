"""
Data Access Layer (Repository Pattern)

Repositories handle all database queries and return domain objects.
They should NOT contain business logic - only data fetching/persistence.
"""

from .api_token_repository import ApiTokenRepository
from .player_availability_repository import PlayerAvailabilityRepository
from .audit_repository import AuditRepository
from .challonge_repository import ChallongeRepository
from .commentator_repository import CommentatorRepository
from .discord_role_mapping_repository import DiscordRoleMappingRepository
from .equipment_repository import EquipmentRepository
from .feedback_repository import FeedbackRepository
from .match_acknowledgment_repository import MatchAcknowledgmentRepository
from .match_repository import MatchRepository
from .match_watcher_repository import MatchWatcherRepository
from .preset_repository import PresetRepository
from .stream_room_repository import StreamRoomRepository
from .tenant_repository import TenantRepository
from .tenant_membership_repository import TenantMembershipRepository
from .tournament_notification_repository import TournamentNotificationRepository
from .telemetry_repository import TelemetryRepository
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
from .webhook_repository import WebhookRepository
from .webhook_delivery_repository import WebhookDeliveryRepository

__all__ = [
    'ApiTokenRepository',
    'PlayerAvailabilityRepository',
    'AuditRepository',
    'ChallongeRepository',
    'CommentatorRepository',
    'DiscordRoleMappingRepository',
    'EquipmentRepository',
    'FeedbackRepository',
    'MatchAcknowledgmentRepository',
    'MatchRepository',
    'MatchWatcherRepository',
    'PresetRepository',
    'StreamRoomRepository',
    'TenantRepository',
    'TenantMembershipRepository',
    'TelemetryRepository',
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
    'WebhookRepository',
    'WebhookDeliveryRepository',
]
