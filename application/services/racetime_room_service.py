"""Racetime Room Service — record lookup for room→tenant routing.

Rooms are created and their status updated by the PR 4/6 lifecycle; this PR
provides the record and the **unscoped by-slug lookup** the inbound-event router
needs. A racetime event carries only the room slug (no tenant), so
:meth:`get_by_slug` resolves the room — and therefore its tenant — before any
tenant context exists, mirroring how an ``ApiToken`` hash routes back to a
tenant.
"""

from typing import Optional

from application.repositories import RacetimeRoomRepository
from models import Match, RacetimeRoom


class RacetimeRoomService:
    """Lookups for :class:`~models.RacetimeRoom` records."""

    def __init__(self) -> None:
        self.repository = RacetimeRoomRepository()

    async def get_by_slug(self, slug: str) -> Optional[RacetimeRoom]:
        """Resolve a room by its globally-unique slug — unscoped, for routing."""
        return await self.repository.get_by_slug((slug or '').strip())

    async def get_for_match(self, match: Match) -> Optional[RacetimeRoom]:
        return await self.repository.get_by_match(match)
