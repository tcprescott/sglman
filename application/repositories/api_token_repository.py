"""
API Token Repository - Data Access Layer

Handles database operations for personal API access tokens.
"""

from datetime import datetime
from typing import List, Optional

from application.repositories._tenant import current_tenant_id
from models import ApiToken, User


class ApiTokenRepository:
    """Repository for API token data access.

    A token belongs to one tenant, but ``get_by_hash`` is intentionally global:
    the API resolves a token *before* any tenant context exists, then sets the
    context from the token's ``tenant_id`` (see ``api/dependencies.py``).
    """

    @staticmethod
    async def create(
        user: User,
        name: str,
        token_hash: str,
        token_prefix: str,
        read_only: bool = False,
        expires_at: Optional[datetime] = None,
    ) -> ApiToken:
        return await ApiToken.create(
            tenant_id=current_tenant_id(),
            user=user,
            name=name,
            token_hash=token_hash,
            token_prefix=token_prefix,
            read_only=read_only,
            expires_at=expires_at,
        )

    @staticmethod
    async def get_by_id(token_id: int) -> Optional[ApiToken]:
        # Scoped: a user can only manage (revoke) their own tenant's tokens.
        return await ApiToken.get_or_none(id=token_id, tenant_id=current_tenant_id())

    @staticmethod
    async def get_by_hash(token_hash: str) -> Optional[ApiToken]:
        """Return the token matching this hash, with its owning user prefetched.

        GLOBAL by design (token_hash is globally unique) — the caller sets tenant
        context from the resolved token afterwards.
        """
        return await ApiToken.get_or_none(token_hash=token_hash).prefetch_related('user')

    @staticmethod
    async def list_for_user(user: User) -> List[ApiToken]:
        """Active (non-revoked) tokens for a user in the current tenant, newest first."""
        return await ApiToken.filter(
            user=user, revoked_at=None, tenant_id=current_tenant_id()
        ).order_by('-created_at')

    @staticmethod
    async def touch_last_used(token: ApiToken, when: datetime) -> None:
        token.last_used_at = when
        await token.save(update_fields=['last_used_at'])

    @staticmethod
    async def revoke(token: ApiToken, when: datetime) -> None:
        token.revoked_at = when
        await token.save(update_fields=['revoked_at'])
