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
from .match_acknowledgment_repository import MatchAcknowledgmentRepository
from .match_repository import MatchRepository
from .match_watcher_repository import MatchWatcherRepository
from .stream_room_repository import StreamRoomRepository
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
from .volunteer_shift_repository import VolunteerShiftRepository

__all__ = [
    'ApiTokenRepository',
    'PlayerAvailabilityRepository',
    'AuditRepository',
    'ChallongeRepository',
    'CommentatorRepository',
    'MatchAcknowledgmentRepository',
    'MatchRepository',
    'MatchWatcherRepository',
    'StreamRoomRepository',
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
    'VolunteerShiftRepository',
]
