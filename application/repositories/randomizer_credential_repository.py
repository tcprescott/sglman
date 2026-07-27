"""
Randomizer Credential Repository - Data Access Layer

Handles database operations for a tenant's own randomizer API credentials.
"""

from typing import List, Optional, Set, Tuple

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id, scoped
from models import RandomizerCredential


class RandomizerCredentialRepository(TenantScopedRepository[RandomizerCredential]):
    """Repository for RandomizerCredential data access."""

    model = RandomizerCredential

    async def list_all(self) -> List[RandomizerCredential]:
        return await scoped(RandomizerCredential.all()).order_by('randomizer', 'key')

    async def get_by_natural_key(self, randomizer: str, key: str) -> Optional[RandomizerCredential]:
        """Resolve a credential by its per-tenant natural key (randomizer, key)."""
        return await RandomizerCredential.get_or_none(
            tenant_id=current_tenant_id(), randomizer=randomizer, key=key
        )

    async def upsert(self, randomizer: str, key: str, value: str) -> RandomizerCredential:
        credential, _ = await RandomizerCredential.update_or_create(
            tenant_id=current_tenant_id(), randomizer=randomizer, key=key,
            defaults={'value': value},
        )
        return credential

    async def delete_by_natural_key(self, randomizer: str, key: str) -> int:
        return await scoped(
            RandomizerCredential.filter(randomizer=randomizer, key=key)
        ).delete()

    async def configured_pairs(self) -> Set[Tuple[str, str]]:
        """Every ``(randomizer, key)`` this tenant holds a non-blank value for."""
        rows = await scoped(
            RandomizerCredential.exclude(value='')
        ).values_list('randomizer', 'key')
        return {(randomizer, key) for randomizer, key in rows}
