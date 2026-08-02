"""Player-initiated match creation, split out of ``match_service``.

Pure code motion to keep ``match_service`` under the file-length guideline —
``MatchRequestMixin`` is composed into :class:`MatchService` and reaches its
repositories, ``participants``, and ``_seed_acknowledgments`` through that
composed class, the same way :class:`CancellationMixin` does.
"""

from typing import List, Optional

from application.errors import require_found
from application.events import EventType, match_live
from application.services.audit_service import AuditActions
from application.services.match.match_request_guard import assert_player_requests_allowed
from application.utils.timezone import parse_local_datetime
from models import Match, User


class MatchRequestMixin:
    async def submit_match_request(
        self,
        tournament_id: int,
        scheduled_date: str,
        scheduled_time: str,
        player_ids: List[int],
        actor: User,
        comment: Optional[str] = None,
        *,
        title: Optional[str] = None,
        from_bracket: bool = False,
    ) -> Match:
        """Player-initiated match creation.

        Allowed when the actor is a player in the new match (typically self-vs-opponent
        in a tournament they're enrolled in). Bypasses the TA/Staff CRUD gate but
        does not grant Tournament Admin powers.

        ``from_bracket`` is set **only** by ``BracketService.schedule_bracket_match``
        and ``ChallongeService.schedule_challonge_match``, which have already
        authorized the actor as one of the matchup's entrants. It skips the
        tournament's ``allow_player_match_requests`` toggle because scheduling
        through the bracket *is* the sanctioned path that toggle exists to force.
        Never accept it from a request body.

        ``title`` is likewise caller-supplied rather than user-supplied — see
        ``create_match`` for what it replaces.
        """
        if actor is None:
            raise PermissionError("Login required to submit a match request")
        if actor.id not in player_ids:
            raise PermissionError("You may only submit match requests where you are a player")

        if not player_ids:
            raise ValueError("Match must have at least one player")

        tournament = require_found(
            await self.tournament_repository.get_by_id(tournament_id),
            f"Tournament {tournament_id}",
        )
        if not from_bracket:
            assert_player_requests_allowed(tournament)

        try:
            scheduled_at = parse_local_datetime(scheduled_date, scheduled_time)
        except ValueError as e:
            raise ValueError(f"Invalid date/time format: {e}") from e

        await self.assert_within_tournament_hours(scheduled_at, tournament_id)

        # Resolve every player before touching the match row so a missing user
        # doesn't leave an orphan Match behind.
        players = await self.participants.resolve_users(player_ids)

        match = await self.repository.create(
            tournament_id=tournament_id,
            scheduled_at=scheduled_at,
            comment=comment,
            title=title,
        )
        await self.participants.ensure_enrolled(tournament_id, players)
        for user in players:
            await self.repository.add_player(match, user)

        await self.audit_service.write_and_publish(
            actor,
            AuditActions.MATCH_REQUESTED,
            {
                'match_id': match.id,
                'tournament_id': tournament_id,
                'player_ids': player_ids,
            },
            EventType.MATCH_CREATED,
        )

        await self._seed_acknowledgments(match, player_ids, actor)

        await self.match_schedule_service.notify_match_scheduled(match, rescheduled=False)

        match_live.publish(match.id, match_live.CREATED)

        return match
