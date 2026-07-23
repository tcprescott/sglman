"""Bracket Repository — data access for the four native-bracket models.

Pure data access (no business logic, audit, or notifications). One repository
spans :class:`Bracket`, :class:`BracketEntrant`, :class:`BracketEntry`, and
:class:`BracketMatch` — they are one aggregate the lifecycle drives together, so
a single tenant-scoped repository keeps their queries in one place. Reads scope
through the ``_tenant`` helper; custom creates stamp the ambient tenant.
"""

from typing import List, Optional

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id, scoped
from models import Bracket, BracketEntrant, BracketEntry, BracketMatch


class BracketRepository(TenantScopedRepository[Bracket]):
    """Data access for brackets, entrants, entries, and matches."""

    model = Bracket

    # --- Bracket ---------------------------------------------------------
    async def get_bracket(self, bracket_id: int) -> Optional[Bracket]:
        return await scoped(Bracket.filter(id=bracket_id)).first()

    async def list_for_tournament(self, tournament_id: int) -> List[Bracket]:
        return await scoped(
            Bracket.filter(tournament_id=tournament_id)
        ).order_by('stage_order')

    async def get_stage(self, tournament_id: int, stage_order: int) -> Optional[Bracket]:
        return await scoped(
            Bracket.filter(tournament_id=tournament_id, stage_order=stage_order)
        ).first()

    # --- BracketEntrant --------------------------------------------------
    async def create_entrant(self, **fields) -> BracketEntrant:
        return await BracketEntrant.create(tenant_id=current_tenant_id(), **fields)

    async def get_entrant(self, entrant_id: int) -> Optional[BracketEntrant]:
        return await scoped(BracketEntrant.filter(id=entrant_id)).first()

    async def list_entrants(self, tournament_id: int) -> List[BracketEntrant]:
        return await scoped(
            BracketEntrant.filter(tournament_id=tournament_id)
        ).order_by('display_name')

    # --- BracketEntry ----------------------------------------------------
    async def create_entry(self, **fields) -> BracketEntry:
        return await BracketEntry.create(tenant_id=current_tenant_id(), **fields)

    async def get_entry(self, entry_id: int) -> Optional[BracketEntry]:
        return await scoped(BracketEntry.filter(id=entry_id)).first()

    async def list_entries(self, bracket_id: int) -> List[BracketEntry]:
        return await scoped(
            BracketEntry.filter(bracket_id=bracket_id)
        ).order_by('seed', 'id')

    async def list_active_entries(self, bracket_id: int) -> List[BracketEntry]:
        from models import BracketEntryStatus
        return await scoped(
            BracketEntry.filter(bracket_id=bracket_id, status=BracketEntryStatus.ACTIVE)
        ).order_by('seed', 'id')

    async def get_entry_for_entrant(
        self, bracket_id: int, entrant_id: int
    ) -> Optional[BracketEntry]:
        return await scoped(
            BracketEntry.filter(bracket_id=bracket_id, entrant_id=entrant_id)
        ).first()

    # --- BracketMatch ----------------------------------------------------
    async def create_match(self, **fields) -> BracketMatch:
        return await BracketMatch.create(tenant_id=current_tenant_id(), **fields)

    async def get_match(self, match_id: int) -> Optional[BracketMatch]:
        return await scoped(BracketMatch.filter(id=match_id)).first()

    async def list_matches(self, bracket_id: int) -> List[BracketMatch]:
        return await scoped(
            BracketMatch.filter(bracket_id=bracket_id)
        ).order_by('round', 'position')

    async def get_match_at(
        self, bracket_id: int, round: int, position: int
    ) -> Optional[BracketMatch]:
        return await scoped(
            BracketMatch.filter(bracket_id=bracket_id, round=round, position=position)
        ).first()
