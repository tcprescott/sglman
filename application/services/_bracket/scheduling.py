"""Bracket scheduling mixin: the seam that mirrors the Challonge integration.

Split out of ``bracket_service.py`` as pure code motion (see that module's
docstring). ``SchedulingMixin`` is composed into :class:`BracketService`; its
methods reach siblings (including ``report_result`` defined on another mixin)
and ``self.repository`` through that composed class.
"""

from typing import Any, List, Optional

from application.errors import require_found
from models import BracketMatch, BracketMatchState, Match, User


class SchedulingMixin:
    # -- B9: scheduling seam (mirrors the Challonge integration) ----------
    async def list_open_matches_for_user(
        self, user_id: int, tournament_id: Optional[int] = None
    ) -> List[BracketMatch]:
        """OPEN, not-yet-scheduled bracket matches the user can play.

        Peer of ``ChallongeService.list_unscheduled_matches_for_user``: OPEN
        matches where the user is one of the two entrants, restricted to the ones
        whose *both* entrants resolve to a linked ``user`` (only those are
        schedulable into a real ``Match``).
        """
        matches = await self.repository.open_matches_for_user(user_id, tournament_id)
        return [m for m in matches if self._both_entrants_linked(m)]

    @staticmethod
    def _both_entrants_linked(bracket_match: BracketMatch) -> bool:
        e1, e2 = bracket_match.entry1, bracket_match.entry2
        return (
            e1 is not None
            and e2 is not None
            and e1.entrant is not None
            and e2.entrant is not None
            and e1.entrant.user_id is not None
            and e2.entrant.user_id is not None
        )

    async def schedule_bracket_match(
        self, actor: Optional[User], bracket_match_id: int, **match_kwargs: Any
    ) -> Match:
        """Schedule an OPEN bracket match into a real ``Match``.

        Mirror of ``ChallongeService.schedule_challonge_match``: the bracket match
        must be OPEN and unscheduled, and both entrants must be linked to a
        ``user``. Delegates match creation to :class:`MatchService` (the same seam
        Challonge uses, so seeding/crew/notifications behave identically), then
        links the resulting ``Match`` back onto the bracket match's ``match`` FK.
        """
        bracket_match = require_found(
            await self.repository.get_match_with_entrants(bracket_match_id),
            "Bracket match",
        )
        if bracket_match.match_id is not None:
            raise ValueError("This bracket match has already been scheduled.")
        if bracket_match.state != BracketMatchState.OPEN:
            raise ValueError("This bracket match isn't ready to schedule yet.")
        if not self._both_entrants_linked(bracket_match):
            raise ValueError("Both players must be linked to schedule this match.")

        from application.services.match_service import MatchService

        match = await MatchService().create_match(
            tournament_id=bracket_match.bracket.tournament_id,
            player_ids=[
                bracket_match.entry1.entrant.user_id,
                bracket_match.entry2.entrant.user_id,
            ],
            actor=actor,
            **match_kwargs,
        )
        bracket_match.match = match
        await bracket_match.save()
        return match

    async def advance_if_linked(self, match: Match, actor: Optional[User]) -> bool:
        """Advance the native bracket when a confirmed ``Match`` mirrors one.

        Peer of ``ChallongeService.push_result_if_linked``. Guard-and-skip:
        returns False when there is no actor or the match isn't linked to a
        bracket match. Otherwise maps the match's winner (the ``MatchPlayers`` row
        with ``finish_rank == 1``) to the winning :class:`BracketEntry` and records
        it through the un-gated :meth:`_record_result` (skipped when the bracket
        match is already COMPLETE). This is deliberately NOT routed through the
        staff-gated :meth:`report_result`: the confirming actor here may be a
        Proctor or the system user, and their confirmation must still advance the
        bracket — matching the Challonge peer ``push_match_result``, which has no
        staff gate. Returns True whenever the match is linked.
        """
        if actor is None:
            return False
        bracket_match = await self.repository.get_bracket_match_for_match(match.id)
        if bracket_match is None:
            return False
        if bracket_match.state == BracketMatchState.COMPLETE:
            return True

        await match.fetch_related('players')
        winner_player = next(
            (p for p in match.players if p.finish_rank == 1), None
        )
        if winner_player is None:
            return True

        winner_entry = next(
            (
                entry
                for entry in (bracket_match.entry1, bracket_match.entry2)
                if entry is not None
                and entry.entrant is not None
                and entry.entrant.user_id == winner_player.user_id
            ),
            None,
        )
        if winner_entry is not None:
            await self._record_result(actor, bracket_match.id, winner_entry.id)
        return True
