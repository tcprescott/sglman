"""
Preset Repository - Data Access Layer

Handles database operations for tenant-scoped seed-rolling presets.
"""

from typing import List, Optional

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id, scoped
from models import Preset


class PresetRepository(TenantScopedRepository[Preset]):
    """Repository for Preset data access."""

    model = Preset

    async def get_by_natural_key(self, randomizer: str, name: str) -> Optional[Preset]:
        """Resolve a preset by its per-tenant natural key (randomizer, name)."""
        return await Preset.get_or_none(
            tenant_id=current_tenant_id(), randomizer=randomizer, name=name
        )

    async def list_all(self) -> List[Preset]:
        return await scoped(Preset.all()).order_by('randomizer', 'name')

    async def list_by_randomizer(self, randomizer: str) -> List[Preset]:
        return await scoped(Preset.filter(randomizer=randomizer)).order_by('name')
