"""Race Room Profile Repository — tenant-scoped reusable room settings.

Standard tenant scoping: reads are constrained to the current tenant and writes
are stamped with it via the ``_tenant`` helpers, so a profile from another tenant
is never visible or linkable.
"""

from typing import Any, List, Optional

from application.repositories._tenant import current_tenant_id, scoped
from models import RaceRoomProfile


class RaceRoomProfileRepository:
    """Data access for tenant-scoped :class:`~models.RaceRoomProfile` rows."""

    async def list_all(self) -> List[RaceRoomProfile]:
        return await scoped(RaceRoomProfile.all()).order_by('name')

    async def get_by_id(self, profile_id: int) -> Optional[RaceRoomProfile]:
        return await RaceRoomProfile.get_or_none(id=profile_id, tenant_id=current_tenant_id())

    async def get_by_name(self, name: str) -> Optional[RaceRoomProfile]:
        return await RaceRoomProfile.get_or_none(tenant_id=current_tenant_id(), name=name)

    async def create(self, **fields: Any) -> RaceRoomProfile:
        return await RaceRoomProfile.create(tenant_id=current_tenant_id(), **fields)

    async def update(self, profile: RaceRoomProfile, **fields: Any) -> RaceRoomProfile:
        for key, value in fields.items():
            setattr(profile, key, value)
        await profile.save()
        return profile

    async def delete(self, profile: RaceRoomProfile) -> None:
        await profile.delete()
