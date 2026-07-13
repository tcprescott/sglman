"""
Preset Repository - Data Access Layer

Handles database operations for tenant-scoped seed-rolling presets.
"""

from typing import Any, List, Optional

from application.repositories._tenant import current_tenant_id, scoped
from models import Preset


class PresetRepository:
    """Repository for Preset data access."""

    async def get_by_id(self, preset_id: int) -> Optional[Preset]:
        return await Preset.get_or_none(id=preset_id, tenant_id=current_tenant_id())

    async def get_by_natural_key(self, randomizer: str, name: str) -> Optional[Preset]:
        """Resolve a preset by its per-tenant natural key (randomizer, name)."""
        return await Preset.get_or_none(
            tenant_id=current_tenant_id(), randomizer=randomizer, name=name
        )

    async def list_all(self) -> List[Preset]:
        return await scoped(Preset.all()).order_by('randomizer', 'name')

    async def list_by_randomizer(self, randomizer: str) -> List[Preset]:
        return await scoped(Preset.filter(randomizer=randomizer)).order_by('name')

    async def create(self, **fields: Any) -> Preset:
        return await Preset.create(tenant_id=current_tenant_id(), **fields)

    async def update(self, preset: Preset, **fields: Any) -> Preset:
        for key, value in fields.items():
            setattr(preset, key, value)
        await preset.save()
        return preset

    async def delete(self, preset: Preset) -> None:
        await preset.delete()
