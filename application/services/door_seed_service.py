"""
Door Seed Service - Business Logic Layer

Reads the Door Randomizer seeds Wizzrobe hosts (``SeedGenerationService`` rolls
them) for the patcher page and its downloads. Who may read a spoiler is the
rule here: ``public`` is anyone with the link, ``staff`` is this community's
staff (and super-admins), ``none`` is nobody, because it was never kept.
"""

from typing import Optional

from application.errors import NotFoundError, require_found
from application.repositories.door_seed_repository import DoorSeedRepository
from application.services.auth_service import AuthService
from application.utils.door_seed_store import DoorSeedStore
from models import DoorSeed, User


class DoorSeedService:
    def __init__(self, store: Optional[DoorSeedStore] = None) -> None:
        self.store = store or DoorSeedStore()

    async def get_seed(self, token: str) -> DoorSeed:
        return require_found(await DoorSeedRepository.get_by_token(token), 'Seed')

    @staticmethod
    async def can_read_spoiler(seed: DoorSeed, user: Optional[User]) -> bool:
        if seed.spoiler_access == 'public':
            return True
        if seed.spoiler_access == 'staff':
            return await AuthService.is_staff(user)
        return False

    async def spoiler_for(self, seed: DoorSeed, user: Optional[User]) -> bytes:
        if not await self.can_read_spoiler(seed, user):
            raise NotFoundError('Spoiler not found.')
        return require_found(await self.store.get_spoiler(seed.token), 'Spoiler')

    async def public_spoiler(self, token: str) -> Optional[bytes]:
        """The spoiler for the signed-out download route, only where it is public."""
        try:
            seed = await DoorSeedRepository.get_by_token_any_tenant(token)
        except ValueError:
            return None
        if seed is None or seed.spoiler_access != 'public':
            return None
        return await self.store.get_spoiler(token)

    async def patch(self, token: str) -> Optional[bytes]:
        try:
            return await self.store.get_patch(token)
        except ValueError:
            return None

    async def base_patch(self, version: str) -> Optional[bytes]:
        try:
            return await self.store.get_base_patch(version)
        except ValueError:
            return None
