"""
MCP OAuth Repository - Data Access Layer

Registered OAuth clients and pending authorization codes for the MCP server's
authorization server.

Every method here is deliberately **global** — neither model carries a tenant.
An OAuth grant authenticates a user platform-wide; the community a given MCP
tool call acts in is named by that call, not by the credential. See
:mod:`models.mcp`.
"""

from datetime import datetime
from typing import List, Optional

from models import McpAuthorizationCode, McpOAuthClient, User


class McpAuthRepository:
    """Repository for MCP OAuth client and authorization-code data access."""

    @staticmethod
    async def create_client(
        client_id: str,
        client_name: str,
        redirect_uris: List[str],
        grant_types: List[str],
        response_types: List[str],
        token_endpoint_auth_method: str = 'none',
        scope: Optional[str] = None,
    ) -> McpOAuthClient:
        """Register a client. Global — clients belong to no tenant."""
        return await McpOAuthClient.create(
            client_id=client_id,
            client_name=client_name,
            redirect_uris=redirect_uris,
            grant_types=grant_types,
            response_types=response_types,
            token_endpoint_auth_method=token_endpoint_auth_method,
            scope=scope,
        )

    @staticmethod
    async def get_client(client_id: str) -> Optional[McpOAuthClient]:
        """Look up a registered client. Global — no tenant context exists here."""
        return await McpOAuthClient.get_or_none(client_id=client_id)

    @staticmethod
    async def create_code(
        code_hash: str,
        client: McpOAuthClient,
        user: User,
        redirect_uri: str,
        redirect_uri_provided_explicitly: bool,
        code_challenge: str,
        expires_at: datetime,
        code_challenge_method: str = 'S256',
        scope: Optional[str] = None,
        resource: Optional[str] = None,
    ) -> McpAuthorizationCode:
        """Persist a pending authorization code. Global — no tenant."""
        return await McpAuthorizationCode.create(
            code_hash=code_hash,
            client=client,
            user=user,
            redirect_uri=redirect_uri,
            redirect_uri_provided_explicitly=redirect_uri_provided_explicitly,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            expires_at=expires_at,
            scope=scope,
            resource=resource,
        )

    @staticmethod
    async def get_code(code_hash: str) -> Optional[McpAuthorizationCode]:
        """Fetch an authorization code by hash. Global — no tenant context."""
        return await McpAuthorizationCode.get_or_none(
            code_hash=code_hash
        ).prefetch_related('client', 'user')

    @staticmethod
    async def consume_code(code: McpAuthorizationCode, when: datetime) -> None:
        """Mark a code used. Paired with the service's re-read so a replayed
        code is refused even inside its expiry window."""
        code.consumed_at = when
        await code.save(update_fields=['consumed_at'])

    @staticmethod
    async def purge_expired_codes(now: datetime) -> int:
        """Delete codes past their expiry. Global housekeeping."""
        return await McpAuthorizationCode.filter(expires_at__lt=now).delete()
