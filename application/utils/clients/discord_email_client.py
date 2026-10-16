"""Discord OAuth with the ``email`` scope, used only to fill in a notification address.

Sign-in itself asks Discord for ``identify`` alone. When someone presses "Use my
Discord email" on their profile, this one extra authorization adds ``email``,
reads ``/users/@me`` once (id, email, and Discord's ``verified`` flag) and
discards the token.
"""

from __future__ import annotations

from typing import Any, Dict

from application.utils.clients.oauth_identity_client import (
    OAuthIdentityClient,
    ProviderConfig,
    opt_str,
)
from application.utils.clients.oauth_identity_client import (
    build_authorize_url as _build_authorize_url,
)

AUTHORIZE_URL = 'https://discord.com/oauth2/authorize'
TOKEN_URL = 'https://discord.com/api/oauth2/token'
USERINFO_URL = 'https://discord.com/api/users/@me'
SCOPE = 'identify email'


class DiscordEmailError(Exception):
    """Discord refused the token exchange or returned an unexpected identity."""


def build_authorize_url(client_id: str, redirect_uri: str, scope: str, state: str) -> str:
    return _build_authorize_url(AUTHORIZE_URL, client_id, redirect_uri, scope, state)


def _extract_identity(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict) or not payload.get('id'):
        raise DiscordEmailError('Discord returned no account')
    return {
        'user_id': opt_str(payload.get('id')),
        'username': payload.get('username'),
        'email': payload.get('email'),
        'verified': bool(payload.get('verified')),
    }


class DiscordEmailClient(OAuthIdentityClient):
    config = ProviderConfig(
        label='Discord',
        token_url=TOKEN_URL,
        userinfo_url=USERINFO_URL,
        error_class=DiscordEmailError,
        extract_identity=_extract_identity,
    )


class MockDiscordEmailClient(DiscordEmailClient):
    """MOCK_DISCORD stand-in: a verified address for whoever is signed in."""

    def __init__(self, *args, **kwargs):
        super().__init__('mock', 'mock')

    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        return {'access_token': 'mock'}

    async def get_me(self, access_token: str) -> Dict[str, Any]:
        return {'user_id': 'mock', 'username': 'mock', 'email': 'player@example.com', 'verified': True}
