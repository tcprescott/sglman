"""Bracket Service - Business Logic Layer (native brackets, docs/brackets-plan.md).

Owns the bracket lifecycle: authoring a stage (create/update/delete while DRAFT),
managing the tournament-level roster (entrants) and per-stage participation
(entries), and the generate-then-persist ``start`` that turns a seeded field into
a persisted :class:`BracketMatch` graph via the pure structural engines. After
start, elimination advancement is plain pointer-following over the persisted
rows (B7); Swiss/round-robin re-pair per round.

``BracketService`` is a thin composer: it keeps ``__init__`` (wiring the
repository + audit service), the shared helpers, and the roster/enrollment CRUD,
while the lifecycle logic lives in per-concern mixins under
``application/services/_bracket/`` (generation, advancement, completion,
multistage, scheduling). The split is pure code motion — every method resolves
``self.repository`` / ``self.audit_service`` and sibling methods through this one
composed class, so callers still ``from application.services import
BracketService`` and use it unchanged.
"""

from typing import Any, Dict, List, Optional, Union

from application.errors import require_found
from application.events import Event, EventType, event_bus
from application.repositories import BracketRepository
from application.services._bracket.advancement import AdvancementMixin
from application.services._bracket.completion import CompletionMixin
from application.services._bracket.generation import GenerationMixin
from application.services._bracket.multistage import MultiStageMixin
from application.services._bracket.scheduling import SchedulingMixin
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.bracket_config import validate_bracket_config
from application.tenant_context import require_tenant_id
from models import (
    Bracket,
    BracketEntrant,
    BracketEntrantStatus,
    BracketEntry,
    BracketEntryStatus,
    BracketFormat,
    BracketMatch,
    BracketState,
    Tournament,
    User,
)


class BracketService(
    GenerationMixin,
    AdvancementMixin,
    CompletionMixin,
    MultiStageMixin,
    SchedulingMixin,
):
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

    @staticmethod
    def _ensure_no_challonge_link(tournament: Tournament) -> None:
        """Reject a native bracket when the tournament is already on Challonge.

        A tournament uses a native bracket OR a Challonge link, never both — the
        symmetric guard lives in ``ChallongeService.link_tournament``.
        """
        if tournament.challonge_tournament_id:
            raise ValueError(
                "This tournament is already linked to a Challonge bracket; a "
                "tournament uses a native bracket or a Challonge link, never both."
            )

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
        tournament = await self._require_tournament(tournament_id)
        self._ensure_no_challonge_link(tournament)

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
        """Set per-entry seeds (``entry_id → seed``). DRAFT-only.

        Rejects a seed below 1 or one that collides with another entry's seed in
        the same bracket, so a duplicate can never collapse two entrants onto one
        engine slot (silently dropping a player) at ``start_bracket``.
        """
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Only Staff can manage brackets",
        )
        bracket = await self._require_bracket(bracket_id)
        if bracket.state != BracketState.DRAFT:
            raise ValueError("Can only reseed a DRAFT bracket")

        entries = await self.repository.list_entries(bracket_id)
        entry_by_id = {e.id: e for e in entries}

        # Resolve the full per-entry seeding that would result from applying the
        # requested changes, then validate the whole set before writing anything.
        resulting: Dict[int, Optional[int]] = {e.id: e.seed for e in entries}
        for entry_id, seed in seeds.items():
            if entry_id not in entry_by_id:
                require_found(
                    await self.repository.get_entry(entry_id), "Entry"
                )
                raise ValueError("Entry belongs to a different bracket")
            if seed is not None and seed < 1:
                raise ValueError("A seed must be 1 or greater")
            resulting[entry_id] = seed

        seen: Dict[int, int] = {}
        for eid, seed in resulting.items():
            if seed is None:
                continue
            if seed in seen:
                raise ValueError(
                    f"Seed {seed} is assigned to more than one entry"
                )
            seen[seed] = eid

        for entry_id, seed in seeds.items():
            entry = entry_by_id[entry_id]
            entry.seed = seed
            await entry.save()
