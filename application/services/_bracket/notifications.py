"""Bracket notifications: the matchup-ready DM, and series context for the rest.

One new player-facing message and one existing set made richer (D7). The rule is
narrow on purpose: **a DM is sent when it asks the recipient to act.** Scheduling
is the one thing in a bracket only the entrants can do — bracket-run tournaments
run with ``allow_player_match_requests`` off, so the bracket dialog is their sole
route to a booking — and it is therefore the only thing that earns its own DM.
Advancing and being eliminated earn none; the bracket shows those.

That rule also removes a carve-out. A losers-bracket drop needs no special
handling: a winners-bracket loser simply gets the ready DM when their losers
matchup opens, by the same trigger as everyone else.

``BracketNotificationMixin`` is composed into :class:`BracketService` and reaches
``self.repository`` and sibling methods through it. Every send goes out on
``discord_queue``, which re-binds the enqueueing request's ``tenant_scope`` in its
worker, and every one is best-effort: a Discord problem must never abort the
advancement that triggered it.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from application.services.bracket_engines.round_names import RoundNode, round_names
from application.services.discord import discord_queue
from application.utils.discord_embeds import matchup_ready_embed
from application.utils.discord_messages import matchup_ready_dm
from application.utils.tenant_urls import tenant_url
from models import (
    Bracket,
    BracketFormat,
    BracketMatch,
    BracketMatchGameState,
    BracketMatchState,
)

logger = logging.getLogger(__name__)


class BracketNotificationMixin:
    # -- round naming ------------------------------------------------------
    async def round_name_for(self, bracket: Bracket, round_number: int) -> str:
        """The human name of one round of a stage — "Semifinals", "Losers Round 2".

        Naming is structural (which round is the winners final, how deep the
        losers bracket runs, which match is the grand final), so it needs the
        stage's graph; :meth:`BracketRepository.round_links` is the lean
        projection for it. One query.
        """
        rows = await self.repository.round_links(bracket.id)
        names = round_names(
            [
                RoundNode(
                    id=r['id'], round=r['round'],
                    winner_to_id=r['winner_to_id'], loser_to_id=r['loser_to_id'],
                )
                for r in rows
            ],
            double_elim=bracket.format == BracketFormat.DOUBLE_ELIM,
        )
        return names.get(round_number) or f'Round {round_number}'

    # -- series context for the ordinary match DMs -------------------------
    async def bracket_line_for_match(self, match_id: int) -> str:
        """"Semifinals · Game 2 of 3 · Series 1-0" for a match, or '' if not a game.

        Folded into every existing match DM (``scheduled``, ``rescheduled``,
        ``checked_in``, ``cancelled``, ``state_changed``) so a bracket game's
        notification stops being indistinguishable from a casual scheduled match.
        Returns '' — never raises — for the vast majority of matches, which no
        bracket scheduled, and for any lookup that fails: a missing context line
        must not cost a player their match DM.
        """
        line, _ = await self.match_dm_context(match_id)
        return line

    async def match_dm_context(self, match_id: int) -> Tuple[str, bool]:
        """``(bracket_line, frees_a_slot)`` for one match, in a single lookup.

        The cancellation DM needs both facts and needs them *before* the row is
        deleted, so they are resolved together rather than by two passes over the
        same game row. ``frees_a_slot`` predicts what
        :meth:`SchedulingMixin.release_game_if_linked` will do — the game exists
        and is still ``SCHEDULED`` — which is what lets the DM say "the matchup is
        open to reschedule" instead of "nothing further is needed from you".
        """
        try:
            game = await self.repository.get_game_for_match(match_id)
            if game is None:
                return '', False
            frees = game.state == BracketMatchGameState.SCHEDULED
            bracket_match = game.bracket_match
            bracket = await self._require_bracket(bracket_match.bracket_id)
            best_of = self.resolve_best_of(bracket, bracket_match)
            parts = [await self.round_name_for(bracket, bracket_match.round)]
            if best_of > 1:
                parts.append(f'Game {game.game_number} of {best_of}')
                games = await self.repository.list_games(bracket_match.id)
                e1, e2 = self._standing_from(games, bracket_match)
                if e1 or e2:
                    parts.append(f'Series {max(e1, e2)}-{min(e1, e2)}')
            return ' · '.join(parts), frees
        except Exception:  # noqa: BLE001 - a DM must not fail over its subtitle
            logger.exception('bracket DM context lookup failed for match %s', match_id)
            return '', False

    async def matchup_summary(self, match_id: int) -> Optional[Dict[str, Any]]:
        """What a scheduled ``Match`` is *for*, for the admin match editor (U4).

        ``{bracket_id, bracket_name, round_name, game_number, best_of, standing,
        entrants: [{name, seed}], stakes}`` — or ``None`` when the match backs no
        bracket game. ``stakes`` is "Winner to Semifinals", resolved by following
        ``winner_to`` and naming that round; '' for a final, which has no onward
        pointer and where "this decides it" is already obvious from the name.

        The editor previously showed only the link picker, so staff editing a
        game had no way to see which game of what series they were changing.
        """
        game = await self.repository.get_game_for_match(match_id)
        if game is None:
            return None
        resolved = await self.repository.get_match_with_entrants(
            game.bracket_match_id
        )
        if resolved is None:
            return None
        bracket = resolved.bracket
        best_of = self.resolve_best_of(bracket, resolved)
        games = await self.repository.list_games(resolved.id)
        e1, e2 = self._standing_from(games, resolved)
        return {
            'bracket_id': bracket.id,
            'bracket_name': bracket.name,
            'round_name': await self.round_name_for(bracket, resolved.round),
            'game_number': game.game_number,
            'best_of': best_of,
            'standing': f'{max(e1, e2)}-{min(e1, e2)}' if (e1 or e2) else '',
            'entrants': [
                {
                    'name': entry.entrant.display_name if entry and entry.entrant else 'TBD',
                    'seed': entry.seed if entry else None,
                }
                for entry in (resolved.entry1, resolved.entry2)
            ],
            'stakes': await self._stakes(bracket, resolved),
        }

    async def _stakes(self, bracket: Bracket, bracket_match: BracketMatch) -> str:
        """"Winner to Semifinals", or '' when nothing follows this matchup."""
        if bracket_match.winner_to_id is None:
            return ''
        target = await self.repository.get_match(bracket_match.winner_to_id)
        if target is None:
            return ''
        return f'Winner to {await self.round_name_for(bracket, target.round)}'

    # -- the matchup-ready DM ----------------------------------------------
    async def notify_matchup_ready(
        self, bracket_match: BracketMatch, *, rebook: bool = False,
    ) -> None:
        """DM both entrants that they have a matchup to schedule.

        Fired at the moment a matchup becomes bookable: the ``PENDING → OPEN``
        transition in ``_settle_match``, the grand-final reset opening in
        ``_advance_after_result``, each round-1 / Swiss pairing at generation, and
        — with ``rebook`` — a game whose slot was released back (D3).

        Keyed on the *transition* rather than on the state, so a matchup whose two
        slots fill at different times is announced once. Silent when either slot
        is still an unlinked placeholder: there is nobody to tell, and the DM will
        fire when the entrant is linked and the matchup re-settles.
        """
        try:
            if bracket_match.state != BracketMatchState.OPEN:
                return
            resolved = await self.repository.get_match_with_entrants(bracket_match.id)
            if resolved is None or not self._both_entrants_linked(resolved):
                return

            bracket = resolved.bracket
            tournament = bracket.tournament
            round_name = await self.round_name_for(bracket, resolved.round)
            best_of = self.resolve_best_of(bracket, resolved)
            schedule_url = await self._schedule_url(bracket.id)

            for entry, opponent in (
                (resolved.entry1, resolved.entry2),
                (resolved.entry2, resolved.entry1),
            ):
                discord_queue.enqueue(self._send_matchup_ready(
                    user=entry.entrant.user,
                    opponent_name=opponent.entrant.display_name,
                    opponent_seed=opponent.seed,
                    tournament_name=tournament.name,
                    round_name=round_name,
                    best_of=best_of,
                    schedule_url=schedule_url,
                    rebook=rebook,
                ))
        except Exception:  # noqa: BLE001 - never block the advancement that fired it
            logger.exception(
                'matchup-ready notification failed for bracket match %s',
                getattr(bracket_match, 'id', None),
            )

    async def notify_matchup_reopened(
        self, bracket_match: BracketMatch, *, reason: str = '',
    ) -> None:
        """The released-game variant: the matchup is bookable again (U3a).

        A no-op once the series is decided or the matchup left ``OPEN`` — the
        clinch teardown releases nothing (its games are already ``CANCELLED``),
        but a staff override can settle a matchup whose game is then cancelled,
        and telling those two to rebook a series that is over would be wrong.
        """
        fresh = await self.repository.get_match(bracket_match.id)
        if fresh is None or fresh.state != BracketMatchState.OPEN:
            return
        await self.notify_matchup_ready(fresh, rebook=True)

    async def notify_open_matchups(self, bracket: Bracket) -> None:
        """Announce every already-bookable matchup of a freshly-started stage.

        Generation writes round 1 straight to ``OPEN`` rather than transitioning
        into it, so the per-transition hook never sees those — without this, the
        entrants who need the DM most (nobody has told them anything yet) would be
        the only ones who never got it. Disjoint from the transition hook by
        construction: ``_settle_match`` is not on the generation path.
        """
        for bracket_match in await self.repository.list_open_matches(bracket.id):
            await self.notify_matchup_ready(bracket_match)

    @staticmethod
    async def _schedule_url(bracket_id: int) -> str:
        """Absolute deep link to the bracket view, or '' if the tenant is unknown.

        Absolute and tenant-qualified because the DM is read outside any request
        context: a bare ``/brackets/12`` would be meaningless in Discord, and the
        platform-host path prefix (or a tenant's own domain) is exactly what
        :func:`tenant_url` resolves. Best-effort — the message degrades to "on the
        bracket" rather than losing the DM.
        """
        from application.services.tenant_service import TenantService
        from application.tenant_context import get_current_tenant_id

        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return ''
        tenant = await TenantService.get_by_id(tenant_id)
        return tenant_url(tenant, f'/brackets/{bracket_id}') if tenant else ''

    @staticmethod
    async def _send_matchup_ready(
        *,
        user: Any,
        opponent_name: str,
        opponent_seed: Optional[int],
        tournament_name: str,
        round_name: str,
        best_of: int,
        schedule_url: str,
        rebook: bool,
    ) -> None:
        """One entrant's DM. Honours the ``dm_notifications`` opt-out."""
        from application.services.discord.discord_service import DiscordService
        from application.services.match.match_schedule_service import (
            _community_name,
            _dm_opt_ok,
        )

        if not _dm_opt_ok(user, require_opt_in=True):
            return
        message = matchup_ready_dm(
            tournament_name, round_name, opponent_name,
            opponent_seed=opponent_seed, best_of=best_of,
            schedule_url=schedule_url, rebook=rebook,
        )
        embed = matchup_ready_embed(
            tournament=tournament_name,
            round_name=round_name,
            opponent=(
                f'{opponent_name} (#{opponent_seed})' if opponent_seed else opponent_name
            ),
            community_name=await _community_name(),
            best_of=best_of,
            schedule_url=schedule_url or None,
            rebook=rebook,
        )
        success, err = await DiscordService().send_dm(
            user.discord_id, message, embed=embed,
        )
        if not success:
            logger.warning(
                'matchup-ready DM failed for %s: %s', user.discord_id, err,
            )
