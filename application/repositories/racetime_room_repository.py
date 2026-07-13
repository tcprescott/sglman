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
from models import Match, RaceRoomStatus, RacetimeRoom


class RacetimeRoomRepository:
    """Data access for racetime race-room records."""

    async def get_by_slug(self, slug: str) -> Optional[RacetimeRoom]:
        """Resolve a room by its globally-unique slug — **unscoped** on purpose.

        Inbound racetime events carry no tenant, so slug → room is the entry
        point the routing layer uses before any tenant context exists (mirrors
        ``ApiTokenRepository.get_by_hash``).
        """
        return await RacetimeRoom.get_or_none(slug=slug).prefetch_related('tenant')

    async def list_open_all(self) -> List[RacetimeRoom]:
        """Every not-yet-terminal room across all tenants — **unscoped**.

        Used by the runtime on boot to re-adopt live rooms so a redeploy does
        not orphan them. Cross-tenant on purpose (like :meth:`get_by_slug`); the
        caller re-establishes each room's tenant scope from ``room.tenant_id``.
        """
        return await RacetimeRoom.filter(
            status__in=[RaceRoomStatus.OPEN, RaceRoomStatus.IN_PROGRESS],
        ).prefetch_related('tenant').order_by('id')

    async def matches_due_for_auto_open(self, window_start: Any, window_end: Any) -> List[Match]:
        """Candidate matches for the auto-open worker — **unscoped** cross-tenant.

        Returns not-yet-finished matches on auto-create tournaments scheduled in
        the ``[window_start, window_end]`` band, with players/users/tournament
        prefetched so the worker can re-check each tournament's lead time and the
        linked-entrant eligibility without more queries. Intentionally
        tenant-agnostic (like the volunteer-reminder scan); the worker binds each
        match's tenant before acting.
        """
        return await Match.filter(
            scheduled_at__gte=window_start,
            scheduled_at__lte=window_end,
            finished_at__isnull=True,
            tournament__racetime_auto_create_rooms=True,
        ).prefetch_related(
            'tournament', 'players', 'players__user',
        ).order_by('scheduled_at')

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
