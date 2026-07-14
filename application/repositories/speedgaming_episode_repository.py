"""SpeedGaming Episode Repository — data access for :class:`SpeedGamingEpisode`.

Tenant-scoped staging records for the SG ETL. Reads/writes go through the
``_tenant`` helpers; the worker always runs inside a ``tenant_scope``, so the
ambient tenant is set. Upsert is keyed on the unique ``(tenant, sg_episode_id)``.
"""

from typing import Any, List, Optional

from application.repositories._tenant import current_tenant_id, scoped
from models import SpeedGamingEpisode


class SpeedGamingEpisodeRepository:
    """Data access for SpeedGaming staging episodes."""

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

    async def create(self, **fields: Any) -> SpeedGamingEpisode:
        return await SpeedGamingEpisode.create(tenant_id=current_tenant_id(), **fields)

    async def update(self, episode: SpeedGamingEpisode, **fields: Any) -> SpeedGamingEpisode:
        for key, value in fields.items():
            setattr(episode, key, value)
        await episode.save()
        return episode
