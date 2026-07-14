"""
Racetime Service - Business Logic Layer

Coordinates the racetime.gg account-linking integration: a logged-in user
completes a one-time racetime OAuth login (read scope) so we can record their
verified racetime identity (id / name). Their access token is used once and
discarded — we retain identity only, mirroring the Twitch link.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from application.services.audit_service import AuditActions, AuditService
from application.utils.environment import get_base_url
from application.utils.mock_racetime import is_mock_racetime
from application.utils.racetime_client import (
    IDENTITY_SCOPE,
    MockRacetimeClient,
    RacetimeAPIError,
    RacetimeClient,
    build_authorize_url,
)
from models import User


def _redirect_uri() -> str:
    return os.getenv('RACETIME_REDIRECT_URI') or f"{get_base_url()}/racetime/oauth/callback"


class RacetimeService:
    """Business logic for the racetime.gg account-linking integration."""

    def __init__(self) -> None:
        self.audit_service = AuditService()

    # ------------------------------------------------------------------
    # OAuth configuration / URLs
    # ------------------------------------------------------------------
    @staticmethod
    def is_configured() -> bool:
        """True when the OAuth app credentials are present (or mock is on)."""
        if is_mock_racetime():
            return True
        return bool(os.getenv('RACETIME_CLIENT_ID') and os.getenv('RACETIME_CLIENT_SECRET'))

    @staticmethod
    def player_authorize_url(state: str) -> str:
        return build_authorize_url(
            os.getenv('RACETIME_CLIENT_ID', ''), _redirect_uri(), IDENTITY_SCOPE, state,
        )

    @staticmethod
    def redirect_uri() -> str:
        return _redirect_uri()

    def _oauth_client(self) -> RacetimeClient:
        cls = MockRacetimeClient if is_mock_racetime() else RacetimeClient
        return cls(
            client_id=os.getenv('RACETIME_CLIENT_ID', ''),
            client_secret=os.getenv('RACETIME_CLIENT_SECRET', ''),
        )

    # ------------------------------------------------------------------
    # Player identity linking (called by the racetime OAuth callback)
    # ------------------------------------------------------------------
    async def exchange_player_code(self, code: str) -> Dict[str, Any]:
        """Exchange a user's authorization code and return their identity.

        Returns {'user_id', 'username'}. The token is used once and discarded.
        """
        client = self._oauth_client()
        payload = await client.exchange_code(code, _redirect_uri())
        access = payload.get('access_token')
        if not access:
            raise RacetimeAPIError(f"racetime token response missing access_token: {payload}")
        return await client.get_me(access)

    async def record_player_link(
        self,
        user: User,
        racetime_user_id: str,
        racetime_username: Optional[str],
        actor: User,
    ) -> None:
        rid = (racetime_user_id or '').strip()
        if not rid:
            raise ValueError('A racetime account id is required to link this user.')
        existing = await User.filter(racetime_user_id=rid).exclude(id=user.id).first()
        if existing is not None:
            raise ValueError(f'That racetime account is already linked to {existing.username}.')
        user.racetime_user_id = rid
        user.racetime_username = (racetime_username or '').strip() or None
        user.racetime_linked_at = datetime.now(timezone.utc)
        await user.save()
        await self.audit_service.write_log(
            actor, AuditActions.RACETIME_LINKED,
            {'user_id': user.id, 'racetime_user_id': rid, 'racetime_username': user.racetime_username},
        )

    async def unlink_player(self, user: User, actor: User) -> None:
        user.racetime_user_id = None
        user.racetime_username = None
        user.racetime_linked_at = None
        await user.save()
        await self.audit_service.write_log(
            actor, AuditActions.RACETIME_UNLINKED, {'user_id': user.id},
        )
