"""Data access for hosted Door Randomizer seeds."""

from typing import Optional

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import scoped
from models import DoorSeed


class DoorSeedRepository(TenantScopedRepository[DoorSeed]):
    model = DoorSeed

    @classmethod
    async def get_by_token(cls, token: str) -> Optional[DoorSeed]:
        return await scoped(DoorSeed.filter(token=token)).first()

    @classmethod
    async def get_by_token_any_tenant(cls, token: str) -> Optional[DoorSeed]:
        """Global lookup by token, for the signed-out spoiler download.

        Cross-tenant on purpose: that route has no community in its path, and the
        token itself is the secret that names one seed.
        """
        return await DoorSeed.get_or_none(token=token)
