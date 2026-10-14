"""Nav Preference Repository - Data Access Layer

One member's side menu in the current community: their pins and which menu
sections they left open.
"""

from typing import Any, Optional

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id
from models import NavPreference


class NavPreferenceRepository(TenantScopedRepository[NavPreference]):
    """Data access for :class:`NavPreference`."""

    model = NavPreference

    @staticmethod
    async def get_for_user(user_id: int) -> Optional[NavPreference]:
        return await NavPreference.get_or_none(user_id=user_id, tenant_id=current_tenant_id())

    @staticmethod
    async def upsert(user_id: int, **fields: Any) -> NavPreference:
        row, _ = await NavPreference.update_or_create(
            defaults=fields, user_id=user_id, tenant_id=current_tenant_id())
        return row
