"""Race Room Profile Repository — tenant-scoped reusable room settings.

Standard tenant scoping: reads are constrained to the current tenant and writes
are stamped with it via the ``_tenant`` helpers, so a profile from another tenant
is never visible or linkable.
"""

from typing import List, Optional

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id, scoped
from models import RaceRoomProfile


class RaceRoomProfileRepository(TenantScopedRepository[RaceRoomProfile]):
    """Data access for tenant-scoped :class:`~models.RaceRoomProfile` rows."""

    model = RaceRoomProfile

    async def list_all(self) -> List[RaceRoomProfile]:
        return await scoped(RaceRoomProfile.all()).order_by('name')

    async def get_by_name(self, name: str) -> Optional[RaceRoomProfile]:
        return await RaceRoomProfile.get_or_none(tenant_id=current_tenant_id(), name=name)
