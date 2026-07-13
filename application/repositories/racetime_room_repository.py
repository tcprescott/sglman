"""Racetime Room Repository — data access for :class:`~models.RacetimeRoom`.

Rooms are tenant-scoped data, but the **by-slug lookup is deliberately
unscoped**: inbound racetime events carry only the room slug (no tenant), so the
routing layer must resolve slug → room → tenant with no ambient scope, exactly
like the token-hash lookup that routes an ``ApiToken`` back to its tenant. That
method never calls the ``_tenant`` helpers and says so; the scoped reads/writes
(created by the PR 4/6 lifecycle) use them.
"""

from typing import Any, List, Optional

from application.repositories._tenant import current_tenant_id, scoped
from models import Match, RacetimeRoom


class RacetimeRoomRepository:
    """Data access for racetime race-room records."""

    async def get_by_slug(self, slug: str) -> Optional[RacetimeRoom]:
        """Resolve a room by its globally-unique slug — **unscoped** on purpose.

        Inbound racetime events carry no tenant, so slug → room is the entry
        point the routing layer uses before any tenant context exists (mirrors
        ``ApiTokenRepository.get_by_hash``).
        """
        return await RacetimeRoom.get_or_none(slug=slug).prefetch_related('tenant')

    async def get_by_id(self, room_id: int) -> Optional[RacetimeRoom]:
        return await RacetimeRoom.get_or_none(id=room_id, tenant_id=current_tenant_id())

    async def get_by_match(self, match: Match) -> Optional[RacetimeRoom]:
        return await scoped(RacetimeRoom.filter(match_id=match.id)).first()

    async def list_all(self) -> List[RacetimeRoom]:
        return await scoped(RacetimeRoom.all()).order_by('-created_at')

    async def create(self, **fields: Any) -> RacetimeRoom:
        return await RacetimeRoom.create(tenant_id=current_tenant_id(), **fields)

    async def update(self, room: RacetimeRoom, **fields: Any) -> RacetimeRoom:
        for key, value in fields.items():
            setattr(room, key, value)
        await room.save()
        return room
