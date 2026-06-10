"""
API Token Service - Business Logic Layer

Issues, lists, revokes, and authenticates personal API access tokens.

Only the SHA-256 hash of a token is persisted; the plaintext is returned
exactly once, at creation. A token authenticates as its owning ``User`` and
inherits that user's permissions; a ``read_only`` token may only be used for
read (GET) endpoints.
"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from application.repositories.api_token_repository import ApiTokenRepository
from application.services.audit_service import AuditActions, AuditService
from models import ApiToken, User

TOKEN_PREFIX = 'sglman_pat_'


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


class ApiTokenService:
    """Service for personal API access token operations."""

    def __init__(self):
        self.repository = ApiTokenRepository()
        self.audit_service = AuditService()

    async def create_token(
        self,
        actor: User,
        name: str,
        read_only: bool = False,
        expires_at: Optional[datetime] = None,
    ) -> Tuple[ApiToken, str]:
        """Create a token for ``actor``. Returns (token_record, raw_token).

        The raw token is shown only here and never recoverable afterwards.
        """
        if not name or not name.strip():
            raise ValueError("Token name is required")
        if expires_at is not None and expires_at <= datetime.now(timezone.utc):
            raise ValueError("Expiry must be in the future")

        raw_token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token = await self.repository.create(
            user=actor,
            name=name.strip(),
            token_hash=_hash_token(raw_token),
            token_prefix=raw_token[:17],
            read_only=read_only,
            expires_at=expires_at,
        )

        await self.audit_service.write_log(
            actor,
            AuditActions.APITOKEN_CREATED,
            {'token_id': token.id, 'name': token.name, 'read_only': read_only},
        )
        return token, raw_token

    async def list_tokens(self, actor: User) -> List[ApiToken]:
        """List the actor's own active (non-revoked) tokens."""
        return await self.repository.list_for_user(actor)

    async def revoke_token(self, actor: User, token_id: int) -> None:
        token = await self.repository.get_by_id(token_id)
        if token is None or token.revoked_at is not None:
            raise ValueError("Token not found")
        if token.user_id != actor.id:
            raise PermissionError("You can only revoke your own tokens")

        await self.repository.revoke(token, datetime.now(timezone.utc))
        await self.audit_service.write_log(
            actor,
            AuditActions.APITOKEN_REVOKED,
            {'token_id': token.id, 'name': token.name},
        )

    async def authenticate(self, raw_token: str) -> Optional[Tuple[User, ApiToken]]:
        """Resolve a raw bearer token to its (user, token), or None if invalid.

        Rejects unknown, revoked, and expired tokens. Updates ``last_used_at``
        on success.
        """
        if not raw_token:
            return None
        token = await self.repository.get_by_hash(_hash_token(raw_token))
        if token is None or token.revoked_at is not None:
            return None
        now = datetime.now(timezone.utc)
        if token.expires_at is not None and token.expires_at <= now:
            return None

        await self.repository.touch_last_used(token, now)
        return token.user, token
