"""Bracket scheduling mixin: the seam that mirrors the Challonge integration.

Split out of ``bracket_service.py`` as pure code motion (see that module's
docstring). ``SchedulingMixin`` is composed into :class:`BracketService`; its
methods reach siblings (including ``report_result`` defined on another mixin)
and ``self.repository`` through that composed class.
"""

from typing import Any, List, Optional

from application.errors import require_found
from application.events import EventType
from application.services.audit_service import AuditActions
from application.services.auth_service import AuthService
from models import (
    Bracket,
    BracketMatch,
    BracketMatchGameState,
    BracketMatchState,
    Match,
    User,
)


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
        return [
            m for m in matches
            if self._both_entrants_linked(m) and self._has_free_game_slot(m)
        ]

    def _has_free_game_slot(self, bracket_match: BracketMatch) -> bool:
        """Whether this series still has a game left to schedule.

        Reads the ``games`` the repository prefetched — no extra query per match.
        A cancelled game's slot stays consumed, so a series that clinched early
        correctly reports no free slot rather than offering the unplayed game.
        """
        games = list(bracket_match.games)
        best_of = self.resolve_best_of(bracket_match.bracket, bracket_match)
        if self.is_decided(bracket_match, games, best_of):
            return False
        return len({g.game_number for g in games}) < best_of

    @staticmethod
    async def _can_schedule_for_tournament(
        actor: Optional[User], tournament_id: int
    ) -> bool:
        """Whether the actor may schedule on someone else's behalf here."""
        return (
            await AuthService.is_staff(actor)
            or await AuthService.is_tournament_admin(actor, tournament_id)
        )

    @staticmethod
    def _player_schedule_kwargs(match_kwargs: dict) -> dict:
        """Narrow a schedule call to what a player is allowed to set.

        ``ScheduleGameRequest`` carries ``stream_room_id``, so a player can put one
        on the wire. Rejecting is deliberate rather than dropping it silently: a
        request that quietly did less than it said would look like the stage
        assignment had been lost.
        """
        allowed = {'scheduled_date', 'scheduled_time', 'comment'}
        extra = sorted(k for k in match_kwargs if k not in allowed)
        if extra:
            raise ValueError(
                f"Only staff can set {', '.join(extra)} when scheduling a bracket match."
            )
        return dict(match_kwargs)

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
        must be OPEN and both entrants linked to a ``user``. Delegates match
        creation to :class:`MatchService` (the same seam Challonge uses, so
        seeding/crew/notifications behave identically), then records the resulting
        ``Match`` as one :class:`BracketMatchGame`.

        The game number is **assigned here, never passed in** — call this once per
        game to schedule a best-of-N, and all N slots may be booked up front (an
        event programme reserves all three nights of a Bo3, and the ones the
        series never needs are cancelled on the clinch). Raises once every slot is
        taken or the series is already decided.

        **Two authorized callers, two creation paths.** Staff and the tournament's
        admins go through :meth:`MatchService.create_match` and may set crew and a
        stage; the matchup's own entrants go through
        :meth:`MatchService.submit_match_request` with ``from_bracket=True`` — the
        bracket is the only way a player schedules in a bracket-run tournament, so
        that call must bypass the ``allow_player_match_requests`` toggle. Each
        downstream method re-checks its own gate, so the branch here is a router,
        not the only defence. Keep the match creation ahead of ``create_game``:
        reordering the writes so a bracket row lands first would let an
        unauthorized caller mutate the series before the gate runs.
        """
        bracket_match = require_found(
            await self.repository.get_match_with_entrants(bracket_match_id),
            "Bracket match",
        )
        if bracket_match.state == BracketMatchState.COMPLETE:
            # Distinguished from PENDING below: "not ready yet" is wrong and
            # confusing for a series that is already over.
            raise ValueError("This series is already decided.")
        if bracket_match.state != BracketMatchState.OPEN:
            raise ValueError("This bracket match isn't ready to schedule yet.")
        if not self._both_entrants_linked(bracket_match):
            raise ValueError("Both players must be linked to schedule this match.")

        bracket = bracket_match.bracket
        player_ids = [
            bracket_match.entry1.entrant.user_id,
            bracket_match.entry2.entrant.user_id,
        ]
        privileged = await self._can_schedule_for_tournament(actor, bracket.tournament_id)
        if not privileged and (actor is None or actor.id not in player_ids):
            raise PermissionError("You can only schedule your own bracket matches.")

        best_of = self.resolve_best_of(bracket, bracket_match)
        games = await self.repository.list_games(bracket_match_id)
        if self.is_decided(bracket_match, games, best_of):
            raise ValueError("This series is already decided.")
        number = await self.next_game_number(bracket_match, best_of)

        from application.services.match.match_service import MatchService

        title = self._game_title(bracket, bracket_match, number, best_of)
        if privileged:
            match = await MatchService().create_match(
                tournament_id=bracket.tournament_id,
                player_ids=player_ids,
                actor=actor,
                title=title,
                **match_kwargs,
            )
        else:
            player_kwargs = self._player_schedule_kwargs(match_kwargs)
            match = await MatchService().submit_match_request(
                tournament_id=bracket.tournament_id,
                player_ids=player_ids,
                actor=actor,
                title=title,
                from_bracket=True,
                **player_kwargs,
            )
        game = await self.repository.create_game(
            bracket_match_id=bracket_match.id,
            game_number=number,
            match_id=match.id,
            state=BracketMatchGameState.SCHEDULED,
        )
        details = {
            'bracket_id': bracket.id,
            'match_id': bracket_match.id,
            'game_id': game.id,
            'game_number': number,
            'scheduled_match_id': match.id,
        }
        await self.audit_service.write_and_publish(
            actor, AuditActions.BRACKET_GAME_SCHEDULED, details,
            EventType.BRACKET_GAME_SCHEDULED,
        )
        return match

    # -- linking a manually-scheduled match onto a matchup -----------------
    async def list_linkable_matches(self, tournament_id: int) -> List[BracketMatch]:
        """OPEN matchups in a tournament that a ``Match`` could still be linked to.

        Same filter :meth:`list_open_matches_for_user` applies — both entrants
        linked to a user, a game slot still free — but across the whole
        tournament rather than one player's. Backs the admin editor's picker.
        """
        matches = await self.repository.open_matches_for_tournament(tournament_id)
        return [
            m for m in matches
            if self._both_entrants_linked(m) and self._has_free_game_slot(m)
        ]

    async def get_bracket_match_for_match(
        self, match_id: int
    ) -> Optional[BracketMatch]:
        """The matchup a scheduled ``Match`` belongs to, or None.

        Read-only lookup exposed for the admin match editor, which needs to show
        the current link without reaching through ``service.repository``.
        """
        return await self.repository.get_bracket_match_for_match(match_id)

    async def link_match_to_bracket_match(
        self, actor: Optional[User], bracket_match_id: int, match_id: int
    ) -> Any:
        """Record an already-created ``Match`` as the next game of a matchup.

        The staff counterpart of :meth:`schedule_bracket_match`: an admin who
        scheduled a match through the ordinary editor can attach it to the matchup
        it actually settles, instead of re-booking it from the bracket. Staff/TA
        only — a player's route is the bracket itself.

        The player-set check is load-bearing rather than cosmetic:
        ``SeriesMixin._winner_from_ranks`` maps the winner by matching
        ``MatchPlayers.user_id`` against the two entrants, so a mismatched link
        would settle nothing and strand the series with no visible cause.
        """
        bracket_match = require_found(
            await self.repository.get_match_with_entrants(bracket_match_id),
            "Bracket match",
        )
        bracket = bracket_match.bracket
        await self._require_scheduling_privilege(actor, bracket.tournament_id)

        if bracket_match.state == BracketMatchState.COMPLETE:
            raise ValueError("This series is already decided.")
        if bracket_match.state != BracketMatchState.OPEN:
            raise ValueError("This bracket match isn't ready to schedule yet.")
        if not self._both_entrants_linked(bracket_match):
            raise ValueError("Both players must be linked to schedule this match.")

        from application.services.match.match_service import MatchService

        match = require_found(
            await MatchService().get_by_id(match_id), f"Match {match_id}"
        )
        if match.tournament_id != bracket.tournament_id:
            raise ValueError("That match belongs to a different tournament.")
        if await self.repository.get_game_for_match(match.id) is not None:
            raise ValueError("That match is already linked to a bracket matchup.")

        entrant_ids = {
            bracket_match.entry1.entrant.user_id,
            bracket_match.entry2.entrant.user_id,
        }
        match_player_ids = {p.user_id for p in await MatchService().get_match_players(match)}
        if match_player_ids != entrant_ids:
            raise ValueError(
                "That match's players don't match this matchup's entrants."
            )

        best_of = self.resolve_best_of(bracket, bracket_match)
        games = await self.repository.list_games(bracket_match_id)
        if self.is_decided(bracket_match, games, best_of):
            raise ValueError("This series is already decided.")
        number = await self.next_game_number(bracket_match, best_of)

        game = await self.repository.create_game(
            bracket_match_id=bracket_match.id,
            game_number=number,
            match_id=match.id,
            state=BracketMatchGameState.SCHEDULED,
        )
        await self.audit_service.write_and_publish(
            actor, AuditActions.BRACKET_GAME_LINKED,
            {
                'bracket_id': bracket.id,
                'match_id': bracket_match.id,
                'game_id': game.id,
                'game_number': number,
                'scheduled_match_id': match.id,
            },
            EventType.BRACKET_GAME_LINKED,
        )
        return game

    async def unlink_match(self, actor: Optional[User], match_id: int) -> bool:
        """Detach a scheduled ``Match`` from its matchup, leaving the match alone.

        False when the match backs no game. Only a still-SCHEDULED game can be
        detached: removing a settled one would leave the series' win count short
        of what the bracket already advanced on.
        """
        game = await self.repository.get_game_for_match(match_id)
        if game is None:
            return False

        bracket_match = game.bracket_match
        bracket = await self._require_bracket(bracket_match.bracket_id)
        await self._require_scheduling_privilege(actor, bracket.tournament_id)

        if game.state != BracketMatchGameState.SCHEDULED:
            raise ValueError(
                "That game has already been played; its result would be lost."
            )

        details = {
            'bracket_id': bracket.id,
            'match_id': bracket_match.id,
            'game_id': game.id,
            'game_number': game.game_number,
            'scheduled_match_id': match_id,
        }
        await self.repository.delete_game(game.id)
        await self.audit_service.write_and_publish(
            actor, AuditActions.BRACKET_GAME_UNLINKED, details,
            EventType.BRACKET_GAME_UNLINKED,
        )
        return True

    async def _require_scheduling_privilege(
        self, actor: Optional[User], tournament_id: int
    ) -> None:
        if not await self._can_schedule_for_tournament(actor, tournament_id):
            raise PermissionError(
                "Only staff or a tournament admin can link matches to a bracket."
            )

    @staticmethod
    def _game_title(
        bracket: Bracket, bracket_match: BracketMatch, number: int, best_of: int
    ) -> Optional[str]:
        """A self-describing label for one game of a series, or None for a Bo1.

        ``Match.title`` **replaces** the Discord scheduled event's whole title
        (the default template is ``{match}``) and names the racetime room, so a
        bare "Game 2 of 3" would lose the tournament and players entirely. None
        for a best-of-1 keeps every existing event and room name byte-for-byte
        unchanged — only series games get an explicit title.

        Uses the entrants' ``display_name`` so the label matches the bracket UI.
        """
        if best_of <= 1:
            return None
        e1, e2 = bracket_match.entry1, bracket_match.entry2
        return (
            f'{bracket.tournament.name}: '
            f'{e1.entrant.display_name} vs {e2.entrant.display_name} '
            f'— Game {number} of {best_of}'
        )[:255]

    async def advance_if_linked(self, match: Match, actor: Optional[User]) -> bool:
        """Settle a confirmed ``Match`` as its series game; advance on the clinch.

        Peer of ``ChallongeService.push_result_if_linked``, and the name the
        confirm flow calls. The work lives in
        :meth:`SeriesMixin.settle_game_if_linked` — a best-of-1 clinches on its
        single game, so this stayed one code path when series landed.

        Deliberately NOT routed through the staff-gated :meth:`report_result`:
        the confirming actor may be a Proctor or the system user, and their
        confirmation must still advance the bracket — matching the Challonge peer
        ``push_match_result``, which has no staff gate.
        """
        return await self.settle_game_if_linked(match, actor)
