"""Twitch OAuth + Helix transport client.

A thin async ``aiohttp`` wrapper over the two Twitch endpoints we need to link a
user's account: the OAuth token exchange and the Helix ``users`` lookup. It is
deliberately small — we only capture identity (id / login / display name) and
never retain the access token.

The client returns a **normalized** identity dict so the service layer never has
to know the wire shape:

    get_me -> {'user_id', 'username', 'display_name'}
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional
from urllib.parse import quote

import aiohttp

AUTHORIZE_URL = 'https://id.twitch.tv/oauth2/authorize'
OAUTH_EXCHANGE_URL = 'https://id.twitch.tv/oauth2/token'
USERS_URL = 'https://api.twitch.tv/helix/users'


class TwitchAPIError(Exception):
    """Raised when the Twitch API returns an error or unexpected payload."""


def build_authorize_url(client_id: str, redirect_uri: str, scope: str, state: str) -> str:
    """Return the Twitch OAuth authorize URL to redirect the browser to."""
    return (
        f"{AUTHORIZE_URL}"
        f"?client_id={quote(client_id, safe='')}"
        f"&redirect_uri={quote(redirect_uri, safe='')}"
        f"&response_type=code"
        f"&scope={quote(scope, safe='')}"
        f"&state={quote(state, safe='')}"
    )


def _opt_str(value: Any) -> Optional[str]:
    return None if value is None else str(value)


class TwitchClient:
    """Async Twitch OAuth + Helix client."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret

    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange an authorization code for a token payload."""
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(OAUTH_EXCHANGE_URL, data=data) as resp:
                payload = await resp.json()
                if resp.status >= 400:
                    raise TwitchAPIError(
                        f"Twitch token request failed ({resp.status}): {payload}"
                    )
                return payload

    async def get_me(self, access_token: str) -> Dict[str, Any]:
        """Fetch the authenticated Twitch account identity for a raw token.

        Helix requires both the bearer token and the app ``Client-Id`` header.
        """
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Client-Id': self.client_id,
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(USERS_URL, headers=headers) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise TwitchAPIError(f"Twitch users request failed ({resp.status}): {text}")
                import json as _json
                try:
                    payload = _json.loads(text)
                except ValueError as e:
                    raise TwitchAPIError(f"Twitch API returned non-JSON: {text[:200]}") from e
        records = payload.get('data') or []
        if not records:
            raise TwitchAPIError(f"Twitch users response contained no user: {payload}")
        record = records[0]
        return {
            'user_id': _opt_str(record.get('id')),
            'username': record.get('login'),
            'display_name': record.get('display_name'),
        }


# ----------------------------------------------------------------------
# Mock client (MOCK_TWITCH) — a deterministic canned identity so local dev
# can click through link/unlink without a real OAuth app.
# ----------------------------------------------------------------------
_MOCK_IDENTITIES = [
    {'user_id': '20001', 'username': 'mocktwitchone', 'display_name': 'MockTwitchOne'},
    {'user_id': '20002', 'username': 'mocktwitchtwo', 'display_name': 'MockTwitchTwo'},
    {'user_id': '20003', 'username': 'mocktwitchthree', 'display_name': 'MockTwitchThree'},
    {'user_id': '20004', 'username': 'mocktwitchfour', 'display_name': 'MockTwitchFour'},
]


class MockTwitchClient(TwitchClient):
    """Canned client used when MOCK_TWITCH is enabled."""

    def __init__(self, *args, **kwargs):  # noqa: D401 - signature compat
        super().__init__('mock', 'mock')

    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        return {'access_token': 'mock-access', 'token_type': 'bearer', 'expires_in': 14400}

    async def get_me(self, access_token: str) -> Dict[str, Any]:
        # Which canned identity the next link binds to, chosen via env hint so
        # distinct dev users can link to distinct Twitch identities.
        idx = int(os.environ.get('MOCK_TWITCH_IDENTITY', '1'))
        return dict(_MOCK_IDENTITIES[(idx - 1) % len(_MOCK_IDENTITIES)])
