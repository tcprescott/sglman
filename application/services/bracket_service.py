"""Bracket Service - Business Logic Layer (native brackets, docs/brackets-plan.md).

Owns the bracket lifecycle: authoring a stage (create/update/delete while DRAFT),
managing the tournament-level roster (entrants) and per-stage participation
(entries), and the generate-then-persist ``start`` that turns a seeded field into
a persisted :class:`BracketMatch` graph via the pure structural engines. After
start, elimination advancement is plain pointer-following over the persisted
rows (B7); Swiss/round-robin re-pair per round.

This unit (B6) implements authoring, roster, enrollment, and ``start_bracket``.
Result recording, advancement, and completion arrive in B7 and reuse
:meth:`_propagate_winner`.
"""

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple, Union

from application.errors import require_found
from application.events import Event, EventType, event_bus
from application.repositories import BracketRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.bracket_config import validate_bracket_config
from application.services.bracket_engines import get_bracket_engine
from application.services.bracket_engines.base import PairingPlayer
from application.services.bracket_engines.standings import (
    ResultRow,
    StandingsConfig,
    compute_standings,
)
from application.tenant_context import require_tenant_id
from models import (
    Bracket,
    BracketEntrant,
    BracketEntrantStatus,
    BracketEntry,
    BracketEntryStatus,
    BracketFormat,
    BracketMatch,
    BracketMatchState,
    BracketState,
    Tournament,
    User,
)


class BracketService:
    """Service for native-bracket lifecycle operations."""

    def __init__(self) -> None:
        self.repository = BracketRepository()
        self.audit_service = AuditService()

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _coerce_format(fmt: Union[str, BracketFormat]) -> BracketFormat:
        if isinstance(fmt, BracketFormat):
            return fmt
        try:
            return BracketFormat(fmt)
        except ValueError as exc:
            raise ValueError(f"Invalid bracket format: {fmt!r}") from exc

    async def _require_tournament(self, tournament_id: int) -> Tournament:
        return require_found(
            await Tournament.get_or_none(id=tournament_id, tenant_id=require_tenant_id()),
            "Tournament",
        )

    async def _require_bracket(self, bracket_id: int) -> Bracket:
        return require_found(await self.repository.get_bracket(bracket_id), "Bracket")

    # -- bracket authoring ------------------------------------------------
    async def create_bracket(
        self,
        actor: Optional[User],
        tournament_id: int,
        name: str,
        format: Union[str, BracketFormat],
        stage_order: int = 0,
        config: Optional[Dict[str, Any]] = None,
    ) -> Bracket:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        await self._require_tournament(tournament_id)

        if not name or not name.strip():
            raise ValueError("Bracket name is required")

        fmt = self._coerce_format(format)
        config = validate_bracket_config(config)

        if await self.repository.get_stage(tournament_id, stage_order) is not None:
            raise ValueError(f"A bracket stage already exists at stage_order {stage_order}")

        bracket = await self.repository.create(
            tournament_id=tournament_id,
            name=name.strip(),
            format=fmt,
            state=BracketState.DRAFT,
            stage_order=stage_order,
            config=config,
        )

        details = {
            'bracket_id': bracket.id,
            'tournament_id': tournament_id,
            'name': bracket.name,
            'format': fmt.value,
        }
        await self.audit_service.write_log(actor, AuditActions.BRACKET_CREATED, details)
        event_bus.publish(Event.create(EventType.BRACKET_CREATED, details, actor))
        return bracket

    async def update_bracket(
        self,
        actor: Optional[User],
        bracket_id: int,
        name: Optional[str] = None,
        stage_order: Optional[int] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Bracket:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        bracket = await self._require_bracket(bracket_id)
        if bracket.state != BracketState.DRAFT:
            raise ValueError("Only a DRAFT bracket can be edited")

        update_data: Dict[str, Any] = {}
        if name is not None:
            if not name.strip():
                raise ValueError("Bracket name cannot be empty")
            update_data['name'] = name.strip()
        if stage_order is not None and stage_order != bracket.stage_order:
            existing = await self.repository.get_stage(bracket.tournament_id, stage_order)
            if existing is not None and existing.id != bracket.id:
                raise ValueError(
                    f"A bracket stage already exists at stage_order {stage_order}"
                )
            update_data['stage_order'] = stage_order
        if config is not None:
            update_data['config'] = validate_bracket_config(config)

        if update_data:
            bracket = await self.repository.update(bracket, **update_data)
        return bracket

    async def delete_bracket(self, actor: Optional[User], bracket_id: int) -> None:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        bracket = await self._require_bracket(bracket_id)
        if bracket.state != BracketState.DRAFT:
            raise ValueError("Only a DRAFT bracket can be deleted")
        await self.repository.delete(bracket)

    # -- reads ------------------------------------------------------------
    async def get_bracket(self, bracket_id: int) -> Optional[Bracket]:
        return await self.repository.get_bracket(bracket_id)

    async def list_brackets(self, tournament_id: int) -> List[Bracket]:
        return await self.repository.list_for_tournament(tournament_id)

    async def list_matches(self, bracket_id: int) -> List[BracketMatch]:
        return await self.repository.list_matches(bracket_id)

    async def list_entries(self, bracket_id: int) -> List[BracketEntry]:
        return await self.repository.list_entries(bracket_id)

    async def list_entrants(self, tournament_id: int) -> List[BracketEntrant]:
        return await self.repository.list_entrants(tournament_id)

    # -- roster (tournament-level entrants) -------------------------------
    async def add_entrant(
        self,
        actor: Optional[User],
        tournament_id: int,
        display_name: str,
        user_id: Optional[int] = None,
    ) -> BracketEntrant:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        await self._require_tournament(tournament_id)
        if not display_name or not display_name.strip():
            raise ValueError("Entrant display name is required")

        entrant = await self.repository.create_entrant(
            tournament_id=tournament_id,
            display_name=display_name.strip(),
            user_id=user_id,
            status=BracketEntrantStatus.ACTIVE,
        )
        details = {
            'entrant_id': entrant.id,
            'tournament_id': tournament_id,
            'display_name': entrant.display_name,
            'user_id': user_id,
        }
        await self.audit_service.write_log(actor, AuditActions.BRACKET_ENTRANT_ADDED, details)
        event_bus.publish(Event.create(EventType.BRACKET_ENTRANT_ADDED, details, actor))
        return entrant

    async def drop_entrant(self, actor: Optional[User], entrant_id: int) -> BracketEntrant:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        entrant = require_found(await self.repository.get_entrant(entrant_id), "Entrant")
        entrant.status = BracketEntrantStatus.DROPPED
        await entrant.save()
        details = {'entrant_id': entrant.id, 'tournament_id': entrant.tournament_id}
        await self.audit_service.write_log(actor, AuditActions.BRACKET_ENTRANT_DROPPED, details)
        event_bus.publish(Event.create(EventType.BRACKET_ENTRANT_DROPPED, details, actor))
        return entrant

    # -- enrollment (per-stage entries) -----------------------------------
    async def enroll(
        self,
        actor: Optional[User],
        bracket_id: int,
        entrant_id: int,
        seed: Optional[int] = None,
        group_number: Optional[int] = None,
    ) -> BracketEntry:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        bracket = await self._require_bracket(bracket_id)
        if bracket.state != BracketState.DRAFT:
            raise ValueError("Can only enroll into a DRAFT bracket")

        entrant = require_found(await self.repository.get_entrant(entrant_id), "Entrant")
        if entrant.tournament_id != bracket.tournament_id:
            raise ValueError("Entrant belongs to a different tournament")

        if await self.repository.get_entry_for_entrant(bracket_id, entrant_id) is not None:
            raise ValueError("Entrant is already enrolled in this bracket")

        return await self.repository.create_entry(
            bracket_id=bracket_id,
            entrant_id=entrant_id,
            seed=seed,
            group_number=group_number,
            status=BracketEntryStatus.ACTIVE,
        )

    async def set_seeds(
        self,
        actor: Optional[User],
        bracket_id: int,
        seeds: Dict[int, int],
    ) -> None:
        """Set per-entry seeds (``entry_id → seed``). DRAFT-only."""
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        bracket = await self._require_bracket(bracket_id)
        if bracket.state != BracketState.DRAFT:
            raise ValueError("Can only reseed a DRAFT bracket")

        for entry_id, seed in seeds.items():
            entry = require_found(await self.repository.get_entry(entry_id), "Entry")
            if entry.bracket_id != bracket_id:
                raise ValueError("Entry belongs to a different bracket")
            entry.seed = seed
            await entry.save()

    # -- start (generate + persist the match graph) -----------------------
    async def start_bracket(self, actor: Optional[User], bracket_id: int) -> Bracket:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        bracket = await self._require_bracket(bracket_id)
        if bracket.state != BracketState.DRAFT:
            raise ValueError("Only a DRAFT bracket can be started")

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
        """
        n = len(entries)
        used = {e.seed for e in entries if e.seed is not None}
        available = [s for s in range(1, n + 1) if s not in used]
        missing = sorted((e for e in entries if e.seed is None), key=lambda e: e.id)
        for entry, seed in zip(missing, available):
            entry.seed = seed
            await entry.save()
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

    # -- B7: results, advancement, stage completion -----------------------

    _ELIM_FORMATS = (BracketFormat.SINGLE_ELIM, BracketFormat.DOUBLE_ELIM)

    async def report_result(
        self, actor: Optional[User], match_id: int, winner_entry_id: int
    ) -> BracketMatch:
        """Record ``winner_entry_id`` as the winner of an OPEN match, then advance.

        Staff-gated. The match must be OPEN and belong to an ACTIVE bracket, and
        the winner must be one of the match's two entries. After completing the
        match the winner and loser are pushed through the ``winner_to`` /
        ``loser_to`` pointers, downstream slots are settled (auto-advancing
        walkovers), and the stage is auto-completed when an elimination final
        resolves.
        """
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        match = require_found(await self.repository.get_match(match_id), "Match")
        bracket = await self._require_bracket(match.bracket_id)
        if bracket.state != BracketState.ACTIVE:
            raise ValueError("Can only report results for an ACTIVE bracket")
        if match.state != BracketMatchState.OPEN:
            raise ValueError("Only an OPEN match can be reported")
        if winner_entry_id not in (match.entry1_id, match.entry2_id):
            raise ValueError("Winner must be one of the match's two entries")

        winner_entry = require_found(
            await self.repository.get_entry(winner_entry_id), "Entry"
        )
        loser_id = (
            match.entry1_id if winner_entry_id == match.entry2_id else match.entry2_id
        )
        loser_entry = require_found(
            await self.repository.get_entry(loser_id), "Entry"
        )

        match.winner = winner_entry
        match.state = BracketMatchState.COMPLETE
        await match.save()

        details = {
            'bracket_id': bracket.id,
            'match_id': match.id,
            'winner_entry_id': winner_entry_id,
            'loser_entry_id': loser_id,
        }
        await self.audit_service.write_log(
            actor, AuditActions.BRACKET_MATCH_COMPLETED, details
        )
        event_bus.publish(Event.create(EventType.BRACKET_MATCH_COMPLETED, details, actor))

        await self._advance_after_result(bracket, match, winner_entry, loser_entry)
        await self._maybe_complete_stage(bracket, actor)
        return require_found(await self.repository.get_match(match_id), "Match")

    async def _advance_after_result(
        self,
        bracket: Bracket,
        match: BracketMatch,
        winner_entry: BracketEntry,
        loser_entry: BracketEntry,
    ) -> None:
        """Push a completed match's winner/loser through its progression pointers."""
        is_elim = bracket.format in self._ELIM_FORMATS

        reset = await self._gf1_reset(match)
        if reset is not None:
            # Grand Final 1 (double elim): winner_to and loser_to both target the
            # terminal reset match. If the winners-bracket side (slot 1) wins, the
            # title is decided — the reset is never played and the loser is the
            # runner-up. If the losers-bracket side (slot 2) wins, populate and
            # open the reset for the deciding game.
            winner_from_wb = winner_entry.id == match.entry1_id
            if winner_from_wb:
                await self._clear_match_slots(reset)
                await self._set_entry_status(
                    loser_entry, BracketEntryStatus.ELIMINATED
                )
            else:
                await self._set_entry_status(winner_entry, BracketEntryStatus.ACTIVE)
                await self._set_entry_status(loser_entry, BracketEntryStatus.ACTIVE)
                self._place(reset, match.winner_to_slot, winner_entry)
                self._place(reset, match.loser_to_slot, loser_entry)
                reset.state = BracketMatchState.OPEN
                await reset.save()
            return

        if is_elim:
            await self._set_entry_status(winner_entry, BracketEntryStatus.ACTIVE)

        winner_target = await self._propagate_winner(match, winner_entry)

        loser_target: Optional[BracketMatch] = None
        if match.loser_to_id is not None:
            loser_target = await self.repository.get_match(match.loser_to_id)
            if loser_target is not None:
                self._place(loser_target, match.loser_to_slot, loser_entry)
                await loser_target.save()
                if is_elim:
                    await self._set_entry_status(
                        loser_entry, BracketEntryStatus.ACTIVE
                    )
        elif is_elim:
            await self._set_entry_status(loser_entry, BracketEntryStatus.ELIMINATED)

        settled: set = set()
        for target in (winner_target, loser_target):
            if target is None or target.id in settled:
                continue
            settled.add(target.id)
            fresh = await self.repository.get_match(target.id)
            if fresh is not None:
                await self._settle_match(fresh)

    async def _gf1_reset(self, match: BracketMatch) -> Optional[BracketMatch]:
        """Return the reset match iff ``match`` is a double-elim Grand Final 1.

        Structural, since there is no ``is_reset`` column: GF1 is the match whose
        ``winner_to`` and ``loser_to`` point at the *same* target, and that shared
        target is terminal (no onward pointers) — i.e. the reset. The degenerate
        P=2 winners final also points both pointers at the grand final, but that
        target still has onward pointers (into the reset), so it is not mistaken
        for GF1.
        """
        if match.winner_to_id is None or match.winner_to_id != match.loser_to_id:
            return None
        target = await self.repository.get_match(match.winner_to_id)
        if target is None:
            return None
        if target.winner_to_id is None and target.loser_to_id is None:
            return target
        return None

    @staticmethod
    def _place(match: BracketMatch, slot: Optional[int], entry: BracketEntry) -> None:
        if slot == 1:
            match.entry1 = entry
        else:
            match.entry2 = entry

    async def _clear_match_slots(self, match: BracketMatch) -> None:
        """Empty a match's entry slots and reset it to PENDING (idempotent)."""
        match.entry1 = None
        match.entry2 = None
        match.winner = None
        match.state = BracketMatchState.PENDING
        await match.save()

    @staticmethod
    async def _set_entry_status(
        entry: BracketEntry, status: BracketEntryStatus
    ) -> None:
        if entry.status != status:
            entry.status = status
            await entry.save()

    async def _settle_match(self, match: BracketMatch, _depth: int = 0) -> None:
        """Set a match's state after one of its slots changed.

        Both slots filled and not already COMPLETE → OPEN. Exactly one slot
        filled whose empty counterpart has no still-pending feeder → walkover:
        complete it with the present entry and recurse into the target. Otherwise
        → PENDING.
        """
        if _depth > 1000 or match.state == BracketMatchState.COMPLETE:
            return

        has1 = match.entry1_id is not None
        has2 = match.entry2_id is not None

        if has1 and has2:
            match.state = BracketMatchState.OPEN
            await match.save()
            return

        if has1 != has2:
            empty_slot = 2 if has1 else 1
            if await self._slot_can_fill(match.id, empty_slot):
                match.state = BracketMatchState.PENDING
                await match.save()
                return
            present_id = match.entry1_id if has1 else match.entry2_id
            present = await self.repository.get_entry(present_id)
            if present is None:
                match.state = BracketMatchState.PENDING
                await match.save()
                return
            target = await self._propagate_winner(match, present)
            if target is not None:
                fresh = await self.repository.get_match(target.id)
                if fresh is not None:
                    await self._settle_match(fresh, _depth + 1)
            return

        match.state = BracketMatchState.PENDING
        await match.save()

    async def _slot_can_fill(
        self, match_id: int, slot: int, _seen: Optional[set] = None
    ) -> bool:
        """Whether an entry can still arrive in ``slot`` of ``match_id``.

        A slot is fed by not-yet-COMPLETE upstream matches (via their ``winner_to``
        or ``loser_to`` pointers). A winner-feeder can deliver an entry only if it
        will ever have at least one entrant; a loser-feeder only if it will ever be
        a real two-entrant contest. This recurses so that a dead phantom (an
        elimination match both of whose own feeders were byes) is correctly seen
        as unable to fill the slot — turning the downstream lone entrant into a
        walkover instead of an eternally-pending match.
        """
        if _seen is None:
            _seen = set()
        key = (match_id, slot)
        if key in _seen:
            return False
        _seen.add(key)

        for feeder in await self.repository.winner_feeders(match_id, slot):
            if await self._can_produce_winner(feeder, _seen):
                return True
        for feeder in await self.repository.loser_feeders(match_id, slot):
            if await self._can_produce_loser(feeder, _seen):
                return True
        return False

    async def _can_produce_winner(
        self, match: BracketMatch, _seen: set
    ) -> bool:
        if match.state == BracketMatchState.COMPLETE:
            return match.winner_id is not None
        if match.entry1_id is not None or match.entry2_id is not None:
            return True
        return await self._slot_can_fill(
            match.id, 1, _seen
        ) or await self._slot_can_fill(match.id, 2, _seen)

    async def _can_produce_loser(
        self, match: BracketMatch, _seen: set
    ) -> bool:
        if match.state == BracketMatchState.COMPLETE:
            # A completed match yields a loser only if it was a real contest.
            return match.entry1_id is not None and match.entry2_id is not None
        slot1_live = match.entry1_id is not None or await self._slot_can_fill(
            match.id, 1, _seen
        )
        slot2_live = match.entry2_id is not None or await self._slot_can_fill(
            match.id, 2, _seen
        )
        return slot1_live and slot2_live

    async def override_result(
        self, actor: Optional[User], match_id: int, winner_entry_id: int
    ) -> BracketMatch:
        """Staff correction of an already-COMPLETE match's winner.

        Allowed only while no match downstream of this one is already COMPLETE
        (raise otherwise — staff must undo the downstream results first). The new
        winner/loser are re-pushed into the still-uncompleted downstream slots.
        """
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        match = require_found(await self.repository.get_match(match_id), "Match")
        bracket = await self._require_bracket(match.bracket_id)
        if match.state != BracketMatchState.COMPLETE:
            raise ValueError("Can only override a COMPLETE match")
        if winner_entry_id not in (match.entry1_id, match.entry2_id):
            raise ValueError("Winner must be one of the match's two entries")

        downstream_ids = {
            tid for tid in (match.winner_to_id, match.loser_to_id) if tid is not None
        }
        for tid in downstream_ids:
            target = await self.repository.get_match(tid)
            if target is not None and target.state == BracketMatchState.COMPLETE:
                raise ValueError(
                    "A downstream match is already complete; undo it before "
                    "overriding this result"
                )

        winner_entry = require_found(
            await self.repository.get_entry(winner_entry_id), "Entry"
        )
        loser_id = (
            match.entry1_id if winner_entry_id == match.entry2_id else match.entry2_id
        )
        loser_entry = require_found(
            await self.repository.get_entry(loser_id), "Entry"
        )

        match.winner = winner_entry
        await match.save()

        await self._advance_after_result(bracket, match, winner_entry, loser_entry)
        await self._maybe_complete_stage(bracket, actor)

        details = {
            'bracket_id': bracket.id,
            'match_id': match.id,
            'winner_entry_id': winner_entry_id,
            'loser_entry_id': loser_id,
            'override': True,
        }
        await self.audit_service.write_log(
            actor, AuditActions.BRACKET_MATCH_COMPLETED, details
        )
        event_bus.publish(Event.create(EventType.BRACKET_MATCH_COMPLETED, details, actor))
        return require_found(await self.repository.get_match(match_id), "Match")

    async def get_open_matches(self, bracket_id: int) -> List[BracketMatch]:
        """All OPEN (playable) matches of a bracket."""
        return await self.repository.list_open_matches(bracket_id)

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
        target_rounds = self._swiss_target_rounds(bracket, len(entries))
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
