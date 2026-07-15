"""Feature Flag Repository — per-tenant feature-flag rows.

Two access shapes:

* **Scoped** reads/writes for the *ambient* tenant (via the shared
  ``_tenant`` seam) — the hot path every gated page/service guard reads.
* **Explicit-tenant** methods (``*_for_tenant``) used by the super-admin
  ``/platform`` surface, which operates on a chosen tenant and so passes
  ``tenant_id`` deliberately, exactly like the racetime-bot grant repository.
"""

from typing import Dict, List, Optional

from application.repositories._tenant import current_tenant_id, scoped
from models import TenantFeatureFlag


class TenantFeatureFlagRepository:
    """Data access for :class:`~models.TenantFeatureFlag` rows."""

    # --- current-tenant (scoped) ---

    @staticmethod
    async def list_for_current_tenant() -> List[TenantFeatureFlag]:
        return await scoped(TenantFeatureFlag.all())

    @staticmethod
    async def map_for_current_tenant() -> Dict[str, TenantFeatureFlag]:
        """``flag`` key → row, for the ambient tenant (single query)."""
        return {row.flag: row for row in await scoped(TenantFeatureFlag.all())}

    @staticmethod
    async def get_for_current_tenant(flag: str) -> Optional[TenantFeatureFlag]:
        return await scoped(TenantFeatureFlag.filter(flag=flag)).first()

    @staticmethod
    async def set_enabled_for_current_tenant(flag: str, enabled: bool) -> TenantFeatureFlag:
        row = await scoped(TenantFeatureFlag.filter(flag=flag)).first()
        if row is None:
            return await TenantFeatureFlag.create(
                tenant_id=current_tenant_id(), flag=flag, available=False, enabled=enabled,
            )
        row.enabled = enabled
        await row.save(update_fields=['enabled', 'updated_at'])
        return row

    # --- explicit-tenant (deliberately cross-tenant; /platform super-admin) ---

    @staticmethod
    async def list_for_tenant(tenant_id: int) -> List[TenantFeatureFlag]:
        # Deliberately not ``scoped``: the super-admin surface operates on a
        # chosen tenant, so the id is passed explicitly.
        return await TenantFeatureFlag.filter(tenant_id=tenant_id)

    @staticmethod
    async def get_for_tenant(tenant_id: int, flag: str) -> Optional[TenantFeatureFlag]:
        return await TenantFeatureFlag.get_or_none(tenant_id=tenant_id, flag=flag)

    @staticmethod
    async def set_availability_for_tenant(
        tenant_id: int, flag: str, available: bool
    ) -> TenantFeatureFlag:
        row = await TenantFeatureFlag.get_or_none(tenant_id=tenant_id, flag=flag)
        if row is None:
            return await TenantFeatureFlag.create(
                tenant_id=tenant_id, flag=flag, available=available, enabled=False,
            )
        row.available = available
        await row.save(update_fields=['available', 'updated_at'])
        return row
