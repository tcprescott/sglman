"""
Matcherino Login Repository - Data Access Layer

The one stored Matcherino login per tenant that the check-in sync signs in as.
"""

from typing import Optional

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id, scoped
from models import MatcherinoLogin, User


class MatcherinoLoginRepository(TenantScopedRepository[MatcherinoLogin]):
    model = MatcherinoLogin

    @staticmethod
    async def get_current() -> Optional[MatcherinoLogin]:
        return await scoped(MatcherinoLogin.all()).prefetch_related('updated_by').first()

    @staticmethod
    async def upsert(
        refresh_token: str, matcherino_user_id: Optional[str], updated_by: User,
    ) -> MatcherinoLogin:
        login, _ = await MatcherinoLogin.update_or_create(
            tenant_id=current_tenant_id(),
            defaults={
                'refresh_token': refresh_token,
                'matcherino_user_id': matcherino_user_id,
                'updated_by': updated_by,
            },
        )
        return login

    @staticmethod
    async def delete_current() -> int:
        return await scoped(MatcherinoLogin.all()).delete()
