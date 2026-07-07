"""
Twitch Service - Business Logic Layer

Coordinates the Twitch account-linking integration: a logged-in user completes
a one-time Twitch OAuth login so we can record their verified Twitch identity
(id / login / display name). Their access token is used once and discarded — we
retain identity only.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from application.services.audit_service import AuditActions, AuditService
from application.utils.environment import get_base_url
from application.utils.mock_twitch import is_mock_twitch
from application.utils.twitch_client import (
    MockTwitchClient,
    TwitchAPIError,
    TwitchClient,
    build_authorize_url,
)
from models import User

# Basic public identity (id / login / display name via helix/users) needs no
# scope; an empty scope keeps the consent screen minimal.
_PLAYER_SCOPES = ''


def _redirect_uri() -> str:
    return os.getenv('TWITCH_REDIRECT_URI') or f"{get_base_url()}/twitch/oauth/callback"


class TwitchService:
    """Business logic for the Twitch account-linking integration."""

    def __init__(self) -> None:
        self.audit_service = AuditService()

    # ------------------------------------------------------------------
    # OAuth configuration / URLs
    # ------------------------------------------------------------------
    @staticmethod
    def is_configured() -> bool:
        """True when the OAuth app credentials are present (or mock is on)."""
        if is_mock_twitch():
            return True
        return bool(os.getenv('TWITCH_CLIENT_ID') and os.getenv('TWITCH_CLIENT_SECRET'))

    @staticmethod
    def player_authorize_url(state: str) -> str:
        return build_authorize_url(
            os.getenv('TWITCH_CLIENT_ID', ''), _redirect_uri(), _PLAYER_SCOPES, state,
        )

    @staticmethod
    def redirect_uri() -> str:
        return _redirect_uri()

    def _oauth_client(self) -> TwitchClient:
        cls = MockTwitchClient if is_mock_twitch() else TwitchClient
        return cls(
            client_id=os.getenv('TWITCH_CLIENT_ID', ''),
            client_secret=os.getenv('TWITCH_CLIENT_SECRET', ''),
        )

    # ------------------------------------------------------------------
    # Player identity linking (called by the Twitch OAuth callback)
    # ------------------------------------------------------------------
    async def exchange_player_code(self, code: str) -> Dict[str, Any]:
        """Exchange a user's authorization code and return their identity.

        Returns {'user_id', 'username', 'display_name'}. The token is used once
        and discarded.
        """
        client = self._oauth_client()
        payload = await client.exchange_code(code, _redirect_uri())
        access = payload.get('access_token')
        if not access:
            raise TwitchAPIError(f"Twitch token response missing access_token: {payload}")
        return await client.get_me(access)

    async def record_player_link(
        self,
        user: User,
        twitch_user_id: str,
        twitch_username: Optional[str],
        actor: User,
    ) -> None:
        cuid = (twitch_user_id or '').strip()
        if not cuid:
            raise ValueError('A Twitch account id is required to link this user.')
        existing = await User.filter(twitch_user_id=cuid).exclude(id=user.id).first()
        if existing is not None:
            raise ValueError(f'That Twitch account is already linked to {existing.username}.')
        user.twitch_user_id = cuid
        user.twitch_username = (twitch_username or '').strip() or None
        user.twitch_linked_at = datetime.now(timezone.utc)
        await user.save()
        await self.audit_service.write_log(
            actor, AuditActions.TWITCH_LINKED,
            {'user_id': user.id, 'twitch_user_id': cuid, 'twitch_username': user.twitch_username},
        )

    async def unlink_player(self, user: User, actor: User) -> None:
        user.twitch_user_id = None
        user.twitch_username = None
        user.twitch_linked_at = None
        await user.save()
        await self.audit_service.write_log(
            actor, AuditActions.TWITCH_UNLINKED, {'user_id': user.id},
        )
