"""
API Token Repository - Data Access Layer

Handles database operations for bearer credentials: tenant-bound personal access
tokens (REST) and platform-wide OAuth tokens (MCP).
"""

from datetime import datetime
from typing import List, Optional

from tortoise.expressions import Q

from application.repositories._tenant import current_tenant_id
from models import ApiToken, ApiTokenOrigin, McpOAuthClient, User


class ApiTokenRepository:
    """Repository for API token data access.

    Two kinds of row live here (see :class:`~models.ApiToken`): PATs carry a
    ``tenant`` and serve the REST API; OAuth tokens carry ``tenant=NULL`` and
    serve the MCP server platform-wide. Reads are therefore scoped to
    "the current tenant OR no tenant at all" rather than to the current tenant
    alone — a user's own OAuth tokens must be listable and revocable from any
    community's profile page, since they belong to no single one.

    ``get_by_hash`` is global for a different reason: the token is resolved
    *before* any tenant context exists, on every surface.
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
            origin=ApiTokenOrigin.PAT.value,
        )

    @staticmethod
    async def create_oauth_token(
        user: User,
        client: McpOAuthClient,
        name: str,
        token_hash: str,
        token_prefix: str,
        expires_at: datetime,
        refresh_token_hash: str,
        refresh_expires_at: datetime,
        scope: Optional[str] = None,
    ) -> ApiToken:
        """Create a platform-wide OAuth access token.

        Deliberately global — ``tenant`` stays NULL. An OAuth grant authenticates
        a user across the platform; the community each MCP tool call operates in
        is named by that call, so stamping a tenant here would be wrong, not
        merely redundant. Always ``read_only``: the MCP surface performs no writes.
        """
        return await ApiToken.create(
            tenant_id=None,
            user=user,
            oauth_client=client,
            name=name,
            token_hash=token_hash,
            token_prefix=token_prefix,
            read_only=True,
            origin=ApiTokenOrigin.OAUTH.value,
            expires_at=expires_at,
            refresh_token_hash=refresh_token_hash,
            refresh_expires_at=refresh_expires_at,
            scope=scope,
        )

    @staticmethod
    async def get_by_refresh_hash(refresh_hash: str) -> Optional[ApiToken]:
        """Return the OAuth token holding this refresh-token hash.

        GLOBAL by design, exactly like ``get_by_hash``: a refresh exchange
        arrives with no tenant context and OAuth tokens belong to no tenant.
        """
        return await ApiToken.get_or_none(
            refresh_token_hash=refresh_hash, origin=ApiTokenOrigin.OAUTH.value
        ).prefetch_related('user', 'oauth_client')

    @staticmethod
    async def rotate_refresh(
        token: ApiToken,
        token_hash: str,
        token_prefix: str,
        expires_at: datetime,
        refresh_token_hash: str,
        refresh_expires_at: datetime,
    ) -> None:
        """Re-key an OAuth token in place on a refresh exchange.

        Rotating both halves means a leaked refresh token is single-use: the old
        hashes stop matching the moment the exchange succeeds.
        """
        token.token_hash = token_hash
        token.token_prefix = token_prefix
        token.expires_at = expires_at
        token.refresh_token_hash = refresh_token_hash
        token.refresh_expires_at = refresh_expires_at
        await token.save(
            update_fields=[
                'token_hash', 'token_prefix', 'expires_at',
                'refresh_token_hash', 'refresh_expires_at',
            ]
        )

    @staticmethod
    async def get_by_id(token_id: int) -> Optional[ApiToken]:
        """Fetch a manageable token by id.

        Scoped to this tenant's PATs plus the global (``tenant=NULL``) OAuth
        tokens, so a user can revoke their MCP connections from any community
        they belong to. Ownership is still enforced by the service — this only
        bounds *which rows are addressable*, never *whose*.
        """
        return await ApiToken.filter(
            Q(tenant_id=current_tenant_id()) | Q(tenant_id=None), id=token_id
        ).first()

    @staticmethod
    async def get_by_hash(token_hash: str) -> Optional[ApiToken]:
        """Return the token matching this hash, with its relations prefetched.

        GLOBAL by design (token_hash is globally unique) — the caller sets tenant
        context from the resolved token afterwards.

        ``oauth_client`` is prefetched too: an unfetched FK is a lazy QuerySet,
        not None, so any caller reading ``token.oauth_client.client_id`` on an
        OAuth token would get an AttributeError rather than a value.
        """
        return await ApiToken.get_or_none(
            token_hash=token_hash
        ).prefetch_related('user', 'oauth_client')

    @staticmethod
    async def list_for_user(user: User) -> List[ApiToken]:
        """Active (non-revoked) tokens for a user, newest first.

        This tenant's PATs plus the user's global OAuth tokens, so the profile
        page shows every credential they can revoke from wherever they are.
        """
        return await ApiToken.filter(
            Q(tenant_id=current_tenant_id()) | Q(tenant_id=None),
            user=user,
            revoked_at=None,
        ).order_by('-created_at').prefetch_related('oauth_client')

    @staticmethod
    async def touch_last_used(token: ApiToken, when: datetime) -> None:
        token.last_used_at = when
        await token.save(update_fields=['last_used_at'])

    @staticmethod
    async def revoke(token: ApiToken, when: datetime) -> None:
        token.revoked_at = when
        await token.save(update_fields=['revoked_at'])
