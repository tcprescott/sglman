"""Discord Scheduled Event Repository — data access for :class:`DiscordScheduledEvent`.

Tenant-scoped reconciliation links between an Wizzrobe schedule row and a Discord
Scheduled Event. Reads/writes go through the ``_tenant`` helpers, so the working
set is always **this tenant's own rows** — the shared-guild safety guarantee is
enforced here at the data layer, not just in the reconciler: a query never sees a
sibling tenant's mirrored event, so it can never be updated or cancelled.

The upsert key is the unique ``(tenant, source_type, source_id)``.
"""

from typing import List, Optional

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import scoped
from models import DiscordEventSource, DiscordScheduledEvent


class DiscordScheduledEventRepository(TenantScopedRepository[DiscordScheduledEvent]):
    """Data access for mirrored Discord Scheduled Events (tenant-scoped)."""

    model = DiscordScheduledEvent

    async def list_all(self) -> List[DiscordScheduledEvent]:
        return await scoped(DiscordScheduledEvent.all()).order_by('scheduled_at', 'id')

    async def get_by_id(self, event_id: int) -> Optional[DiscordScheduledEvent]:
        return await scoped(DiscordScheduledEvent.filter(id=event_id)).first()

    async def get_by_source(
        self, source_type: DiscordEventSource, source_id: int
    ) -> Optional[DiscordScheduledEvent]:
        return await scoped(
            DiscordScheduledEvent.filter(source_type=source_type, source_id=source_id)
        ).first()

    async def list_for_source_type(
        self, source_type: DiscordEventSource
    ) -> List[DiscordScheduledEvent]:
        return await scoped(
            DiscordScheduledEvent.filter(source_type=source_type)
        ).order_by('scheduled_at', 'id')
