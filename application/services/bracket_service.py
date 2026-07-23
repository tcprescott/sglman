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

from typing import Any, Dict, List, Optional, Union

from application.errors import require_found
from application.events import Event, EventType, event_bus
from application.repositories import BracketRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.bracket_config import validate_bracket_config
from application.services.bracket_engines import get_bracket_engine
from application.services.bracket_engines.base import PairingPlayer
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

        # Pass 1 — persist a shell BracketMatch per generated node.
        by_coord: Dict[tuple, tuple] = {}
        for gm in graph:
            bm = await self.repository.create_match(
                bracket_id=bracket.id,
                round=gm.round,
                position=gm.position,
                group_number=gm.group_number,
                entry1=seed_to_entry.get(gm.entry1_seed),
                entry2=seed_to_entry.get(gm.entry2_seed),
                state=BracketMatchState.PENDING,
            )
            by_coord[(gm.round, gm.position)] = (bm, gm)

        # Pass 2 — resolve winner_to / loser_to pointers into the persisted graph.
        for bm, gm in by_coord.values():
            changed = False
            if gm.winner_to is not None:
                target = by_coord[(gm.winner_to.round, gm.winner_to.position)][0]
                bm.winner_to = target
                bm.winner_to_slot = gm.winner_to.slot
                changed = True
            if gm.loser_to is not None:
                target = by_coord[(gm.loser_to.round, gm.loser_to.position)][0]
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
