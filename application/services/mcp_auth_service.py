"""
MCP OAuth Service - Business Logic Layer

The authorization server behind ``/mcp``: dynamic client registration,
authorization codes, and the access/refresh tokens they exchange into.

Deliberately free of any MCP SDK types — it deals in this app's models and plain
values, and ``mcpserver/oauth/provider.py`` translates at the boundary. That
keeps the protocol shape in the entry surface where it belongs, and means a SDK
upgrade cannot reach into the service layer.

Everything here is **global**: an OAuth grant authenticates a user across the
platform, and the community a tool call acts in is named by the call. Nothing
in this module reads or writes tenant context.

Only hashes are persisted, for codes and for both halves of a token pair, so a
database disclosure yields nothing replayable.
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from application.errors import NotFoundError
from application.repositories.api_token_repository import ApiTokenRepository
from application.repositories.mcp_auth_repository import McpAuthRepository
from application.services.api_token_service import (
    MCP_REFRESH_PREFIX,
    MCP_TOKEN_PREFIX,
)
from application.services.audit_service import AuditActions, AuditService
from models import ApiToken, ApiTokenOrigin, McpAuthorizationCode, McpOAuthClient, User

logger = logging.getLogger(__name__)

# Short enough that a code left in a browser history or a proxy log is dead by
# the time anyone finds it; long enough for a human to finish a consent screen.
CODE_TTL = timedelta(minutes=5)
ACCESS_TOKEN_TTL = timedelta(hours=1)
REFRESH_TOKEN_TTL = timedelta(days=30)
# A consent screen the user never completes should not pin memory forever.
PENDING_TTL = timedelta(minutes=15)

DEFAULT_SCOPE = 'wizzrobe:read'


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass
class PendingAuthorization:
    """An authorization request parked while the user signs in and approves."""

    client_id: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    code_challenge: str
    scopes: List[str]
    state: Optional[str]
    resource: Optional[str]
    created_at: datetime


# In-process, like the existing cross-host OAuth handoff nonce store, and for
# the same reason: these live for seconds, are meaningless after a restart (the
# user simply reconnects), and the deployment is single-worker by requirement.
# Persisting them would buy nothing and cost a table.
_pending: Dict[str, PendingAuthorization] = {}


class McpAuthService:
    """Authorization-server operations for the MCP surface."""

    def __init__(self) -> None:
        self.repository = McpAuthRepository()
        self.token_repository = ApiTokenRepository()
        self.audit_service = AuditService()

    # --- Clients ---------------------------------------------------------

    async def register_client(
        self,
        client_name: str,
        redirect_uris: List[str],
        grant_types: List[str],
        response_types: List[str],
        token_endpoint_auth_method: str = 'none',
        scope: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> McpOAuthClient:
        """Register a client (RFC 7591 dynamic client registration).

        Open by design — that is what lets a user paste the server URL into
        Claude and have it configure itself. Registering grants nothing: every
        code still requires an interactive, authenticated approval.
        """
        if not redirect_uris:
            raise ValueError('At least one redirect URI is required')
        return await self.repository.create_client(
            client_id=client_id or secrets.token_urlsafe(24),
            client_name=client_name or 'MCP client',
            redirect_uris=redirect_uris,
            grant_types=grant_types or ['authorization_code', 'refresh_token'],
            response_types=response_types or ['code'],
            token_endpoint_auth_method=token_endpoint_auth_method,
            scope=scope or DEFAULT_SCOPE,
        )

    async def get_client(self, client_id: str) -> Optional[McpOAuthClient]:
        return await self.repository.get_client(client_id)

    # --- Authorization request -> consent --------------------------------

    def begin_authorization(self, pending: PendingAuthorization) -> str:
        """Park an authorization request and return its transaction id.

        The id is a capability: whoever holds it can complete *this* request.
        It is not a credential — approving still requires an authenticated
        session, and the code it produces is bound to the client's PKCE
        challenge — so a leaked id cannot be exchanged for anything.
        """
        self._sweep_pending()
        txn_id = secrets.token_urlsafe(24)
        _pending[txn_id] = pending
        return txn_id

    def get_pending(self, txn_id: str) -> PendingAuthorization:
        self._sweep_pending()
        pending = _pending.get(txn_id)
        if pending is None:
            raise NotFoundError(
                'This authorization request has expired. Start again from your MCP client.'
            )
        return pending

    def discard_pending(self, txn_id: str) -> None:
        _pending.pop(txn_id, None)

    @staticmethod
    def _sweep_pending() -> None:
        cutoff = datetime.now(timezone.utc) - PENDING_TTL
        for key in [k for k, v in _pending.items() if v.created_at < cutoff]:
            del _pending[key]

    async def approve(self, txn_id: str, user: User) -> Tuple[str, str, Optional[str]]:
        """Consume a pending request and mint its authorization code.

        Returns ``(raw_code, redirect_uri, state)``. Popping the pending entry
        makes approval single-use, so a re-submitted consent form cannot mint a
        second code for the same request.
        """
        pending = self.get_pending(txn_id)
        self.discard_pending(txn_id)

        client = await self.repository.get_client(pending.client_id)
        if client is None:
            raise NotFoundError('This client is no longer registered.')

        raw_code = secrets.token_urlsafe(32)
        await self.repository.create_code(
            code_hash=_hash(raw_code),
            client=client,
            user=user,
            redirect_uri=pending.redirect_uri,
            redirect_uri_provided_explicitly=pending.redirect_uri_provided_explicitly,
            code_challenge=pending.code_challenge,
            expires_at=datetime.now(timezone.utc) + CODE_TTL,
            scope=' '.join(pending.scopes) if pending.scopes else DEFAULT_SCOPE,
            resource=pending.resource,
        )
        logger.info(
            'MCP authorization approved: user=%s client=%s', user.id, client.client_id
        )
        return raw_code, pending.redirect_uri, pending.state

    # --- Code / token exchange -------------------------------------------

    async def load_code(self, client_id: str, raw_code: str) -> Optional[McpAuthorizationCode]:
        """Fetch a live, unconsumed code belonging to ``client_id``.

        Expiry is re-checked by the SDK's token handler, but a consumed code is
        ours to reject: without that check a stolen code could be replayed
        inside its five-minute window.
        """
        code = await self.repository.get_code(_hash(raw_code))
        if code is None or code.consumed_at is not None:
            return None
        if code.client.client_id != client_id:
            return None
        return code

    async def exchange_code(
        self, code: McpAuthorizationCode
    ) -> Tuple[str, str, int]:
        """Consume a code and issue a token pair.

        Returns ``(access_token, refresh_token, expires_in_seconds)``.
        """
        now = datetime.now(timezone.utc)
        if code.consumed_at is not None:
            raise ValueError('This authorization code has already been used')
        await self.repository.consume_code(code, now)

        access_raw = MCP_TOKEN_PREFIX + secrets.token_urlsafe(32)
        refresh_raw = MCP_REFRESH_PREFIX + secrets.token_urlsafe(32)
        await self.token_repository.create_oauth_token(
            user=code.user,
            client=code.client,
            name=code.client.client_name,
            token_hash=_hash(access_raw),
            token_prefix=access_raw[:17],
            expires_at=now + ACCESS_TOKEN_TTL,
            refresh_token_hash=_hash(refresh_raw),
            refresh_expires_at=now + REFRESH_TOKEN_TTL,
            scope=code.scope,
        )
        await self.audit_service.write_log(
            code.user,
            AuditActions.APITOKEN_CREATED,
            {'client': code.client.client_name, 'origin': ApiTokenOrigin.OAUTH.value},
        )
        return access_raw, refresh_raw, int(ACCESS_TOKEN_TTL.total_seconds())

    async def load_refresh_token(self, client_id: str, raw_refresh: str) -> Optional[ApiToken]:
        token = await self.token_repository.get_by_refresh_hash(_hash(raw_refresh))
        if token is None or token.revoked_at is not None:
            return None
        if token.oauth_client is None or token.oauth_client.client_id != client_id:
            return None
        now = datetime.now(timezone.utc)
        if token.refresh_expires_at is not None and token.refresh_expires_at <= now:
            return None
        return token

    async def exchange_refresh(self, token: ApiToken) -> Tuple[str, str, int]:
        """Rotate both halves of a token pair.

        Rotating the refresh token too — not just the access token — is what
        makes a leaked refresh token single-use: the old hash stops matching the
        moment a legitimate client refreshes, so the theft surfaces as the
        attacker's next call failing rather than as silent shared access.
        """
        now = datetime.now(timezone.utc)
        access_raw = MCP_TOKEN_PREFIX + secrets.token_urlsafe(32)
        refresh_raw = MCP_REFRESH_PREFIX + secrets.token_urlsafe(32)
        await self.token_repository.rotate_refresh(
            token,
            token_hash=_hash(access_raw),
            token_prefix=access_raw[:17],
            expires_at=now + ACCESS_TOKEN_TTL,
            refresh_token_hash=_hash(refresh_raw),
            refresh_expires_at=now + REFRESH_TOKEN_TTL,
        )
        return access_raw, refresh_raw, int(ACCESS_TOKEN_TTL.total_seconds())

    async def load_access_token(self, raw_token: str) -> Optional[ApiToken]:
        result = await ApiTokenRepository.get_by_hash(_hash(raw_token))
        if result is None or result.revoked_at is not None:
            return None
        if result.origin != ApiTokenOrigin.OAUTH.value:
            return None
        now = datetime.now(timezone.utc)
        if result.expires_at is not None and result.expires_at <= now:
            return None
        return result

    async def revoke(self, token: ApiToken) -> None:
        await self.token_repository.revoke(token, datetime.now(timezone.utc))
