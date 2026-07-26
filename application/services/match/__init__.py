"""Match domain services — the scheduling and lifecycle core.

``MatchScheduleService`` owns the state machine (request → seat → start →
finish) via its ``_transition`` template; ``MatchService`` owns CRUD and crew
signup; the rest are the pieces they compose — participant resolution, row
formatting for the tables, the derived status vocabulary, the SpeedGaming field
guard, the settled-bracket-result guard, the bracket-run scheduling guard,
player-initiated requests, cancellation, watchers, and time suggestion.
"""

from application.services.match.bracket_result_guard import (
    assert_bracket_result_editable,
)
from application.services.match.match_cancellation import CancellationMixin
from application.services.match.match_display_service import MatchDisplayService
from application.services.match.match_participants import MatchParticipants
from application.services.match.match_request import MatchRequestMixin
from application.services.match.match_request_guard import assert_player_requests_allowed
from application.services.match.match_schedule_service import MatchScheduleService
from application.services.match.match_service import MatchService
from application.services.match.match_source_guard import assert_sg_fields_unchanged
from application.services.match.match_status import MatchStatus, resolve_matchup
from application.services.match.match_suggestion_service import MatchSuggestionService
from application.services.match.match_watcher_service import MatchWatcherService

__all__ = [
    'CancellationMixin',
    'MatchDisplayService',
    'MatchParticipants',
    'MatchRequestMixin',
    'MatchScheduleService',
    'MatchService',
    'MatchStatus',
    'MatchSuggestionService',
    'MatchWatcherService',
    'assert_bracket_result_editable',
    'assert_player_requests_allowed',
    'assert_sg_fields_unchanged',
    'resolve_matchup',
]
