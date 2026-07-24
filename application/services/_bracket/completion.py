"""Bracket completion mixin: stage completion, round progression, ranking.

Split out of ``bracket_service.py`` as pure code motion (see that module's
docstring). ``CompletionMixin`` is composed into :class:`BracketService`; its
methods reach siblings (including ``_ELIM_FORMATS`` and ``_require_bracket``
defined on other mixins / the composer), ``self.repository`` and
``self.audit_service`` through that composed class.
"""

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from application.events import Event, EventType, event_bus
from application.services.audit_service import AuditActions
from application.services.auth_service import AuthService
from application.services.bracket_engines import get_bracket_engine
from application.services.bracket_engines.base import PairingPlayer
from application.services.bracket_engines.standings import (
    ResultRow,
    StandingsConfig,
    compute_standings,
)
from models import (
    Bracket,
    BracketEntry,
    BracketEntryStatus,
    BracketFormat,
    BracketMatch,
    BracketMatchState,
    BracketState,
    User,
)


class CompletionMixin:
    # -- stage completion / round progression -----------------------------

    async def _maybe_complete_stage(
        self, bracket: Bracket, actor: Optional[User]
    ) -> None:
        """React to a just-recorded result: auto-complete elimination finals and
        generate the next Swiss round. Round robin / Swiss are otherwise finalized
        by the explicit :meth:`complete_stage` call.
        """
        if bracket.state != BracketState.ACTIVE:
            return

        if bracket.format in self._ELIM_FORMATS:
            if await self._elimination_result(bracket) is not None:
                await self._finalize_stage(bracket, actor, tie_breaks=None)
            return

        if bracket.format == BracketFormat.SWISS:
            await self._advance_swiss(bracket, actor)

    async def _advance_swiss(
        self, bracket: Bracket, actor: Optional[User]
    ) -> None:
        matches = await self.repository.list_matches(bracket.id)
        if not matches:
            return
        max_round = max(m.round for m in matches)
        current = [m for m in matches if m.round == max_round]
        if any(m.state != BracketMatchState.COMPLETE for m in current):
            return

        entries = await self.repository.list_entries(bracket.id)
        active_count = sum(
            1 for e in entries if e.status == BracketEntryStatus.ACTIVE
        )
        target_rounds = self._swiss_target_rounds(bracket, active_count)
        if max_round >= target_rounds:
            return

        players = self._swiss_players(bracket, entries, matches)
        engine = get_bracket_engine(bracket.format.value)()
        pairings = engine.pair_round(players, dict(bracket.config or {}))
        if not pairings:
            return

        entry_by_id = {e.id: e for e in entries}
        next_round = max_round + 1
        for position, (ref1, ref2) in enumerate(pairings, start=1):
            if ref2 is None:
                winner = entry_by_id[ref1]
                await self.repository.create_match(
                    bracket_id=bracket.id,
                    round=next_round,
                    position=position,
                    entry1=winner,
                    entry2=None,
                    winner=winner,
                    state=BracketMatchState.COMPLETE,
                )
            else:
                await self.repository.create_match(
                    bracket_id=bracket.id,
                    round=next_round,
                    position=position,
                    entry1=entry_by_id[ref1],
                    entry2=entry_by_id[ref2],
                    state=BracketMatchState.OPEN,
                )

        details = {
            'bracket_id': bracket.id,
            'round': next_round,
            'format': bracket.format.value,
        }
        await self.audit_service.write_log(actor, AuditActions.BRACKET_ADVANCED, details)
        event_bus.publish(Event.create(EventType.BRACKET_ADVANCED, details, actor))

    def _swiss_players(
        self,
        bracket: Bracket,
        entries: List[BracketEntry],
        matches: List[BracketMatch],
    ) -> List[PairingPlayer]:
        results = self._results_from_matches(matches)
        standings = compute_standings(
            [e.id for e in entries], results, self._standings_config(bracket)
        )
        points = {s.ref: s.points for s in standings}

        opponents: Dict[int, set] = defaultdict(set)
        received_bye: Dict[int, bool] = defaultdict(bool)
        for m in matches:
            if m.state != BracketMatchState.COMPLETE:
                continue
            if m.entry1_id is not None and m.entry2_id is not None:
                opponents[m.entry1_id].add(m.entry2_id)
                opponents[m.entry2_id].add(m.entry1_id)
            elif m.entry1_id is not None:
                received_bye[m.entry1_id] = True
            elif m.entry2_id is not None:
                received_bye[m.entry2_id] = True

        return [
            PairingPlayer(
                ref=e.id,
                points=points.get(e.id, 0.0),
                opponents=frozenset(opponents.get(e.id, frozenset())),
                received_bye=received_bye.get(e.id, False),
                can_bye=True,
                dropped=e.status != BracketEntryStatus.ACTIVE,
            )
            for e in entries
        ]

    @staticmethod
    def _swiss_target_rounds(bracket: Bracket, num_entries: int) -> int:
        configured = (bracket.config or {}).get('swiss_rounds')
        if configured:
            return int(configured)
        if num_entries < 2:
            return 1
        return max(1, math.ceil(math.log2(num_entries)))

    async def complete_stage(
        self,
        actor: Optional[User],
        bracket_id: int,
        tie_breaks: Optional[Dict[int, int]] = None,
    ) -> Bracket:
        """Finalize a stage: write every entry's ``final_rank`` and mark COMPLETE.

        For Swiss / round robin this is the staff-triggered finalizer (so staff
        can review standings and resolve ties first). For elimination it is also
        reachable automatically once the final resolves.
        """
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        bracket = await self._require_bracket(bracket_id)
        if bracket.state == BracketState.COMPLETE:
            raise ValueError("Bracket is already complete")
        if bracket.state != BracketState.ACTIVE:
            raise ValueError("Only an ACTIVE bracket can be completed")

        if bracket.format in self._ELIM_FORMATS:
            if await self._elimination_result(bracket) is None:
                raise ValueError("The bracket final has not been decided yet")
        else:
            open_matches = await self.repository.list_open_matches(bracket.id)
            if open_matches:
                raise ValueError("All matches must be played before completing")

        return await self._finalize_stage(bracket, actor, tie_breaks)

    async def _finalize_stage(
        self,
        bracket: Bracket,
        actor: Optional[User],
        tie_breaks: Optional[Dict[int, int]],
    ) -> Bracket:
        matches = await self.repository.list_matches(bracket.id)
        entries = await self.repository.list_entries(bracket.id)

        if bracket.format in self._ELIM_FORMATS:
            await self._rank_elimination(bracket, matches, entries)
        elif bracket.format == BracketFormat.ROUND_ROBIN:
            await self._rank_round_robin(bracket, matches, entries)
        else:
            await self._rank_swiss(bracket, matches, entries, tie_breaks)

        bracket.state = BracketState.COMPLETE
        await bracket.save()

        details = {
            'bracket_id': bracket.id,
            'tournament_id': bracket.tournament_id,
            'format': bracket.format.value,
        }
        await self.audit_service.write_log(actor, AuditActions.BRACKET_COMPLETED, details)
        event_bus.publish(Event.create(EventType.BRACKET_COMPLETED, details, actor))
        return bracket

    async def _elimination_result(
        self, bracket: Bracket, matches: Optional[List[BracketMatch]] = None
    ) -> Optional[Tuple[int, Optional[int], BracketMatch]]:
        """Return ``(champion_id, runner_up_id, deciding_match)`` once the final
        (single elim) or grand final / reset (double elim) resolves, else None.
        """
        if matches is None:
            matches = await self.repository.list_matches(bracket.id)
        terminals = [
            m for m in matches if m.winner_to_id is None and m.loser_to_id is None
        ]
        if not terminals:
            return None

        if bracket.format == BracketFormat.SINGLE_ELIM:
            final = terminals[0]
            if final.state != BracketMatchState.COMPLETE or final.winner_id is None:
                return None
            runner_up = (
                final.entry1_id if final.winner_id == final.entry2_id else final.entry2_id
            )
            return (final.winner_id, runner_up, final)

        reset = terminals[0]
        if reset.state == BracketMatchState.COMPLETE and reset.winner_id is not None:
            runner_up = (
                reset.entry1_id if reset.winner_id == reset.entry2_id else reset.entry2_id
            )
            return (reset.winner_id, runner_up, reset)

        gf1 = next(
            (
                m
                for m in matches
                if m.winner_to_id == reset.id and m.loser_to_id == reset.id
            ),
            None,
        )
        if (
            gf1 is not None
            and gf1.state == BracketMatchState.COMPLETE
            and gf1.winner_id is not None
            and gf1.winner_id == gf1.entry1_id
        ):
            return (gf1.winner_id, gf1.entry2_id, gf1)
        return None

    async def _rank_elimination(
        self,
        bracket: Bracket,
        matches: List[BracketMatch],
        entries: List[BracketEntry],
    ) -> None:
        result = await self._elimination_result(bracket, matches)
        if result is None:
            return
        champion_id, runner_up_id, _ = result

        # Depth of each losing entry's elimination match — the match they lost
        # that has no onward loser pointer (single-elim: their only loss;
        # double-elim: their second loss, in the losers bracket). Deeper (larger
        # |round|) = eliminated later = better placement.
        elim_depth: Dict[int, int] = {}
        for m in matches:
            if m.state != BracketMatchState.COMPLETE or m.winner_id is None:
                continue
            if m.loser_to_id is not None:
                continue
            if m.entry1_id is None or m.entry2_id is None:
                continue
            loser_id = m.entry1_id if m.winner_id == m.entry2_id else m.entry2_id
            elim_depth[loser_id] = abs(m.round)
        elim_depth.pop(champion_id, None)
        if runner_up_id is not None:
            elim_depth.pop(runner_up_id, None)

        seed_of = {e.id: (e.seed if e.seed is not None else 0) for e in entries}
        ordered: List[int] = [champion_id]
        if runner_up_id is not None:
            ordered.append(runner_up_id)
        rest = [e.id for e in entries if e.id not in ordered]
        rest.sort(key=lambda eid: (-elim_depth.get(eid, 0), seed_of.get(eid, 0)))
        ordered.extend(rest)

        ranks = {eid: i + 1 for i, eid in enumerate(ordered)}
        for entry in entries:
            entry.final_rank = ranks.get(entry.id)
            await entry.save()

    async def _rank_round_robin(
        self,
        bracket: Bracket,
        matches: List[BracketMatch],
        entries: List[BracketEntry],
    ) -> None:
        # Each entry's group derives from the matches it played (the engine stamps
        # group_number on matches, not entries); stamp it back onto the entry so a
        # later stage can read group + rank.
        group_of: Dict[int, Optional[int]] = {}
        for m in matches:
            for eid in (m.entry1_id, m.entry2_id):
                if eid is not None:
                    group_of[eid] = m.group_number

        config = self._standings_config(bracket)
        groups = sorted(
            {group_of.get(e.id) for e in entries},
            key=lambda g: (g is None, g),
        )
        for group in groups:
            group_entries = [e for e in entries if group_of.get(e.id) == group]
            group_matches = [
                m
                for m in matches
                if m.group_number == group and m.state == BracketMatchState.COMPLETE
            ]
            results = self._results_from_matches(group_matches)
            standings = compute_standings(
                [e.id for e in group_entries], results, config
            )
            rank_by_ref = {s.ref: s.rank for s in standings}
            for entry in group_entries:
                entry.final_rank = rank_by_ref.get(entry.id)
                entry.group_number = group
                await entry.save()

    async def _rank_swiss(
        self,
        bracket: Bracket,
        matches: List[BracketMatch],
        entries: List[BracketEntry],
        tie_breaks: Optional[Dict[int, int]],
    ) -> None:
        results = self._results_from_matches(matches)
        standings = compute_standings(
            [e.id for e in entries], results, self._standings_config(bracket)
        )
        rank_by_ref = {s.ref: s.rank for s in standings}
        if tie_breaks:
            rank_by_ref.update(tie_breaks)
        for entry in entries:
            entry.final_rank = rank_by_ref.get(entry.id)
            await entry.save()

    @staticmethod
    def _standings_config(bracket: Bracket) -> StandingsConfig:
        config = bracket.config or {}
        kwargs: Dict[str, Any] = {}
        for key in ('win_points', 'draw_points', 'loss_points', 'bye_points', 'omw_floor'):
            value = config.get(key)
            if value is not None:
                kwargs[key] = value
        tiebreakers = config.get('tiebreakers')
        if tiebreakers:
            kwargs['tiebreakers'] = tuple(tiebreakers)
        return StandingsConfig(**kwargs)

    @staticmethod
    def _results_from_matches(matches: List[BracketMatch]) -> List[ResultRow]:
        rows: List[ResultRow] = []
        for m in matches:
            if m.state != BracketMatchState.COMPLETE:
                continue
            if m.entry1_id is None and m.entry2_id is None:
                continue
            if m.entry2_id is None:
                rows.append(ResultRow(ref1=m.entry1_id, winner=m.entry1_id))
            elif m.entry1_id is None:
                rows.append(ResultRow(ref1=m.entry2_id, winner=m.entry2_id))
            else:
                rows.append(
                    ResultRow(ref1=m.entry1_id, ref2=m.entry2_id, winner=m.winner_id)
                )
        return rows
