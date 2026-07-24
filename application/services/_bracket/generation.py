"""Bracket generation mixin: start + match-graph materialization.

Split out of ``bracket_service.py`` as pure code motion (see that module's
docstring). ``GenerationMixin`` is composed into :class:`BracketService`; its
methods reach siblings, ``self.repository`` and ``self.audit_service`` through
that composed class.
"""

from typing import Any, Dict, List, Optional

from application.events import Event, EventType, event_bus
from application.services.audit_service import AuditActions
from application.services.auth_service import AuthService
from application.services.bracket_engines import get_bracket_engine
from application.services.bracket_engines.base import PairingPlayer
from models import (
    Bracket,
    BracketEntry,
    BracketFormat,
    BracketMatch,
    BracketMatchState,
    BracketState,
    User,
)


class GenerationMixin:
    # -- start (generate + persist the match graph) -----------------------
    async def start_bracket(self, actor: Optional[User], bracket_id: int) -> Bracket:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        bracket = await self._require_bracket(bracket_id)
        if bracket.state != BracketState.DRAFT:
            raise ValueError("Only a DRAFT bracket can be started")

        if bracket.stage_order > 0:
            predecessor = await self.repository.get_stage(
                bracket.tournament_id, bracket.stage_order - 1
            )
            if predecessor is None or predecessor.state != BracketState.COMPLETE:
                raise ValueError(
                    "The previous stage must be complete before starting this stage"
                )

        entries = await self.repository.list_active_entries(bracket_id)
        if len(entries) < 2:
            raise ValueError("A bracket needs at least 2 active entries to start")

        seed_to_entry = await self._assign_seeds(entries)
        num_entries = len(entries)

        engine = get_bracket_engine(bracket.format.value)()
        config_dict: Dict[str, Any] = dict(bracket.config or {})

        if bracket.format == BracketFormat.SWISS:
            await self._start_swiss(bracket, entries, engine, config_dict)
        else:
            await self._start_generative(bracket, num_entries, seed_to_entry, engine, config_dict)

        bracket.state = BracketState.ACTIVE
        await bracket.save()

        details = {
            'bracket_id': bracket.id,
            'tournament_id': bracket.tournament_id,
            'format': bracket.format.value,
            'num_entries': num_entries,
        }
        await self.audit_service.write_log(actor, AuditActions.BRACKET_STARTED, details)
        event_bus.publish(Event.create(EventType.BRACKET_STARTED, details, actor))
        return bracket

    async def _assign_seeds(self, entries: List[BracketEntry]) -> Dict[int, BracketEntry]:
        """Ensure every active entry has a contiguous 1..N seed.

        Existing seeds are kept; missing seeds are filled from the unused values
        in ``1..N``, assigned to seed-less entries in entry-id order — so the
        result is deterministic and independent of insertion timing.

        Safety net: after filling, the resulting seed set must be exactly the
        contiguous ``1..N`` with no duplicates. Inconsistent manual seeds (a
        duplicate or out-of-range value) would otherwise collapse or strand an
        engine slot and silently drop an entrant, leaving matches stuck PENDING —
        so this raises a clear ``ValueError`` instead.
        """
        n = len(entries)
        used = {e.seed for e in entries if e.seed is not None}
        available = [s for s in range(1, n + 1) if s not in used]
        missing = sorted((e for e in entries if e.seed is None), key=lambda e: e.id)
        for entry, seed in zip(missing, available):
            entry.seed = seed
            await entry.save()

        assigned = sorted(e.seed for e in entries if e.seed is not None)
        if assigned != list(range(1, n + 1)):
            raise ValueError(
                "Bracket seeds must be a contiguous 1.."
                f"{n} with no duplicates, but the current seeding is "
                f"{sorted((e.seed for e in entries), key=lambda s: (s is None, s))}. "
                "Fix the duplicate or out-of-range seeds before starting."
            )
        return {e.seed: e for e in entries}

    async def _start_generative(
        self,
        bracket: Bracket,
        num_entries: int,
        seed_to_entry: Dict[int, BracketEntry],
        engine: Any,
        config_dict: Dict[str, Any],
    ) -> None:
        graph = engine.generate(num_entries, config_dict)

        # Pass 1 — persist a shell BracketMatch per generated node. Grouped
        # formats (round robin) number positions per group, so offset the
        # persisted position by group to keep (bracket, round, position) unique;
        # these nodes carry no winner_to/loser_to pointers, so the offset only
        # affects storage, not routing.
        by_coord: Dict[tuple, tuple] = {}
        for gm in graph:
            position = gm.position
            if gm.group_number:
                position += (gm.group_number - 1) * 100000
            bm = await self.repository.create_match(
                bracket_id=bracket.id,
                round=gm.round,
                position=position,
                group_number=gm.group_number,
                entry1=seed_to_entry.get(gm.entry1_seed),
                entry2=seed_to_entry.get(gm.entry2_seed),
                state=BracketMatchState.PENDING,
            )
            by_coord[(gm.round, gm.position, gm.group_number)] = (bm, gm)

        # Pass 2 — resolve winner_to / loser_to pointers into the persisted graph.
        for bm, gm in by_coord.values():
            changed = False
            if gm.winner_to is not None:
                target = by_coord[
                    (gm.winner_to.round, gm.winner_to.position, gm.group_number)
                ][0]
                bm.winner_to = target
                bm.winner_to_slot = gm.winner_to.slot
                changed = True
            if gm.loser_to is not None:
                target = by_coord[
                    (gm.loser_to.round, gm.loser_to.position, gm.group_number)
                ][0]
                bm.loser_to = target
                bm.loser_to_slot = gm.loser_to.slot
                changed = True
            if changed:
                await bm.save()

        # Materialize initial state: auto-complete every structural bye and
        # propagate its winner, iterating to a fixpoint (byes never create new
        # byes, so this terminates after each bye is processed once). A downstream
        # match that receives two propagated winners becomes a normal match and is
        # NOT auto-completed.
        processed: set = set()
        changed = True
        while changed:
            changed = False
            for bm, gm in by_coord.values():
                if not gm.is_bye or bm.id in processed:
                    continue
                winner_entry = seed_to_entry.get(gm.entry1_seed) or seed_to_entry.get(gm.entry2_seed)
                if winner_entry is None:
                    processed.add(bm.id)
                    continue
                await self._propagate_winner(bm, winner_entry)
                processed.add(bm.id)
                changed = True

        # Final state pass: both entries present → OPEN, else PENDING.
        for match in await self.repository.list_matches(bracket.id):
            if match.state == BracketMatchState.COMPLETE:
                continue
            if match.entry1_id is not None and match.entry2_id is not None:
                match.state = BracketMatchState.OPEN
            else:
                match.state = BracketMatchState.PENDING
            await match.save()

    async def _start_swiss(
        self,
        bracket: Bracket,
        entries: List[BracketEntry],
        engine: Any,
        config_dict: Dict[str, Any],
    ) -> None:
        entry_by_id = {e.id: e for e in entries}
        players = [PairingPlayer(ref=e.id) for e in entries]
        pairings = engine.pair_round(players, config_dict)

        for position, (ref1, ref2) in enumerate(pairings, start=1):
            if ref2 is None:
                winner = entry_by_id[ref1]
                await self.repository.create_match(
                    bracket_id=bracket.id,
                    round=1,
                    position=position,
                    entry1=winner,
                    entry2=None,
                    winner=winner,
                    state=BracketMatchState.COMPLETE,
                )
            else:
                await self.repository.create_match(
                    bracket_id=bracket.id,
                    round=1,
                    position=position,
                    entry1=entry_by_id[ref1],
                    entry2=entry_by_id[ref2],
                    state=BracketMatchState.OPEN,
                )

    async def _propagate_winner(
        self, match: BracketMatch, winner_entry: BracketEntry
    ) -> Optional[BracketMatch]:
        """Complete ``match`` with ``winner_entry`` and push it into ``winner_to``.

        Sets the winner + COMPLETE state, saves, and — when a ``winner_to`` pointer
        exists — fills the target's ``entry1``/``entry2`` per ``winner_to_slot`` and
        saves the target. Returns the target match (or ``None``). Reused by B7's
        advancement, so it re-fetches the target rather than trusting an in-memory
        pointer object.
        """
        match.winner = winner_entry
        match.state = BracketMatchState.COMPLETE
        await match.save()

        if match.winner_to_id is None:
            return None
        target = await self.repository.get_match(match.winner_to_id)
        if target is None:
            return None
        if match.winner_to_slot == 1:
            target.entry1 = winner_entry
        else:
            target.entry2 = winner_entry
        await target.save()
        return target
