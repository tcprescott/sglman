"""SpeedGaming Event Link Repository — data access for :class:`SpeedGamingEventLink`.

Event links are tenant-scoped config, but the **due-for-sync scan is deliberately
unscoped**: the background worker resolves work across every tenant in one query
(like the volunteer-reminder scan and the racetime auto-open scan), then binds
each link's tenant before touching scoped data. That scan method never calls the
``_tenant`` helpers and says so; the CRUD reads/writes use them.
"""

from typing import Any, List, Optional

from application.repositories._tenant import current_tenant_id, scoped
from models import SpeedGamingEventLink


class SpeedGamingEventLinkRepository:
    """Data access for SpeedGaming event-link config rows."""

    async def list_all(self) -> List[SpeedGamingEventLink]:
        return await scoped(SpeedGamingEventLink.all()).prefetch_related('tournament').order_by('event_slug')

    async def get_by_id(self, link_id: int) -> Optional[SpeedGamingEventLink]:
        return await scoped(
            SpeedGamingEventLink.filter(id=link_id)
        ).prefetch_related('tournament').first()

    async def get_by_natural_key(
        self, tournament_id: int, event_slug: str
    ) -> Optional[SpeedGamingEventLink]:
        return await scoped(
            SpeedGamingEventLink.filter(tournament_id=tournament_id, event_slug=event_slug)
        ).first()

    async def list_active_all(self) -> List[SpeedGamingEventLink]:
        """Every active link across all tenants — **unscoped** cross-tenant.

        The entry point for the sync worker: inbound from a timer, not a request,
        so there is no ambient tenant. The worker re-establishes each link's
        tenant from ``link.tenant_id`` before syncing (mirrors the racetime
        auto-open scan and the volunteer-reminder scan).
        """
        return await SpeedGamingEventLink.filter(active=True).prefetch_related(
            'tournament'
        ).order_by('tenant_id', 'id')

    async def create(self, **fields: Any) -> SpeedGamingEventLink:
        return await SpeedGamingEventLink.create(tenant_id=current_tenant_id(), **fields)

    async def update(self, link: SpeedGamingEventLink, **fields: Any) -> SpeedGamingEventLink:
        for key, value in fields.items():
            setattr(link, key, value)
        await link.save()
        return link

    async def delete(self, link: SpeedGamingEventLink) -> None:
        await link.delete()
