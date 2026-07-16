"""SpeedGaming Episode Repository — data access for :class:`SpeedGamingEpisode`.

Tenant-scoped staging records for the SG ETL. Reads/writes go through the
``_tenant`` helpers; the worker always runs inside a ``tenant_scope``, so the
ambient tenant is set. Upsert is keyed on the unique ``(tenant, sg_episode_id)``.
"""

from typing import List, Optional

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import scoped
from models import SpeedGamingEpisode


class SpeedGamingEpisodeRepository(TenantScopedRepository[SpeedGamingEpisode]):
    """Data access for SpeedGaming staging episodes."""

    model = SpeedGamingEpisode

    async def get_by_sg_id(self, sg_episode_id: str) -> Optional[SpeedGamingEpisode]:
        return await scoped(
            SpeedGamingEpisode.filter(sg_episode_id=sg_episode_id)
        ).first()

    async def get_by_id(self, episode_id: int) -> Optional[SpeedGamingEpisode]:
        return await scoped(SpeedGamingEpisode.filter(id=episode_id)).first()

    async def list_for_link(self, event_link_id: int) -> List[SpeedGamingEpisode]:
        return await scoped(
            SpeedGamingEpisode.filter(event_link_id=event_link_id)
        ).order_by('-scheduled_at')

    async def list_all(self) -> List[SpeedGamingEpisode]:
        return await scoped(SpeedGamingEpisode.all()).order_by('-scheduled_at')
