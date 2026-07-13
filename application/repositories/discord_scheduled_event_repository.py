"""Discord Scheduled Event Repository — data access for :class:`DiscordScheduledEvent`.

Tenant-scoped reconciliation links between an SGLMan schedule row and a Discord
Scheduled Event. Reads/writes go through the ``_tenant`` helpers, so the working
set is always **this tenant's own rows** — the shared-guild safety guarantee is
enforced here at the data layer, not just in the reconciler: a query never sees a
sibling tenant's mirrored event, so it can never be updated or cancelled.

The upsert key is the unique ``(tenant, source_type, source_id)``.
"""

from typing import Any, List, Optional

from application.repositories._tenant import current_tenant_id, scoped
from models import DiscordEventSource, DiscordScheduledEvent


class DiscordScheduledEventRepository:
    """Data access for mirrored Discord Scheduled Events (tenant-scoped)."""

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

    async def create(self, **fields: Any) -> DiscordScheduledEvent:
        return await DiscordScheduledEvent.create(tenant_id=current_tenant_id(), **fields)

    async def update(
        self, event: DiscordScheduledEvent, **fields: Any
    ) -> DiscordScheduledEvent:
        for key, value in fields.items():
            setattr(event, key, value)
        await event.save()
        return event

    async def delete(self, event: DiscordScheduledEvent) -> None:
        await event.delete()
