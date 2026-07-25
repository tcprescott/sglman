"""Match domain services — the scheduling and lifecycle core.

``MatchScheduleService`` owns the state machine (request → seat → start →
finish) via its ``_transition`` template; ``MatchService`` owns CRUD and crew
signup; the rest are the pieces they compose — participant resolution, row
formatting for the tables, the SpeedGaming field guard, cancellation, watchers,
and time suggestion.
"""

from application.services.match.match_cancellation import CancellationMixin
from application.services.match.match_display_service import MatchDisplayService
from application.services.match.match_participants import MatchParticipants
from application.services.match.match_schedule_service import MatchScheduleService
from application.services.match.match_service import MatchService
from application.services.match.match_source_guard import assert_sg_fields_unchanged
from application.services.match.match_suggestion_service import MatchSuggestionService
from application.services.match.match_watcher_service import MatchWatcherService

__all__ = [
    'CancellationMixin',
    'MatchDisplayService',
    'MatchParticipants',
    'MatchScheduleService',
    'MatchService',
    'MatchSuggestionService',
    'MatchWatcherService',
    'assert_sg_fields_unchanged',
]
