"""
API Token Repository - Data Access Layer

Handles database operations for personal API access tokens.
"""

from datetime import datetime
from typing import List, Optional

from models import ApiToken, User


class ApiTokenRepository:
    """Repository for API token data access."""

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
            user=user,
            name=name,
            token_hash=token_hash,
            token_prefix=token_prefix,
            read_only=read_only,
            expires_at=expires_at,
        )

    @staticmethod
    async def get_by_id(token_id: int) -> Optional[ApiToken]:
        return await ApiToken.get_or_none(id=token_id)

    @staticmethod
    async def get_by_hash(token_hash: str) -> Optional[ApiToken]:
        """Return the token matching this hash, with its owning user prefetched."""
        return await ApiToken.get_or_none(token_hash=token_hash).prefetch_related('user')

    @staticmethod
    async def list_for_user(user: User) -> List[ApiToken]:
        """Active (non-revoked) tokens for a user, newest first."""
        return await ApiToken.filter(user=user, revoked_at=None).order_by('-created_at')

    @staticmethod
    async def touch_last_used(token: ApiToken, when: datetime) -> None:
        token.last_used_at = when
        await token.save(update_fields=['last_used_at'])

    @staticmethod
    async def revoke(token: ApiToken, when: datetime) -> None:
        token.revoked_at = when
        await token.save(update_fields=['revoked_at'])
