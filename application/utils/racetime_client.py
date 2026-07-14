"""racetime.gg OAuth transport client.

A thin async ``aiohttp`` wrapper over the two racetime.gg endpoints we need to
link a user's account: the OAuth token exchange and the ``o/userinfo`` identity
lookup. Deliberately small — we only capture identity (id / name) and never
retain the access token.

The client returns a **normalized** identity dict so the service layer never has
to know the wire shape:

    get_me -> {'user_id', 'username'}
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional
from urllib.parse import quote

import aiohttp

RACETIME_BASE = 'https://racetime.gg'
AUTHORIZE_URL = f'{RACETIME_BASE}/o/authorize'
OAUTH_EXCHANGE_URL = f'{RACETIME_BASE}/o/token'
USERINFO_URL = f'{RACETIME_BASE}/o/userinfo'

# The read scope is enough for identity (id / name via o/userinfo); it keeps the
# consent screen minimal and matches "identity only, token discarded".
IDENTITY_SCOPE = 'read'


class RacetimeAPIError(Exception):
    """Raised when the racetime API returns an error or unexpected payload."""


def build_authorize_url(client_id: str, redirect_uri: str, scope: str, state: str) -> str:
    """Return the racetime OAuth authorize URL to redirect the browser to."""
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


class RacetimeClient:
    """Async racetime.gg OAuth client."""

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
                    raise RacetimeAPIError(
                        f"racetime token request failed ({resp.status}): {payload}"
                    )
                return payload

    async def get_me(self, access_token: str) -> Dict[str, Any]:
        """Fetch the authenticated racetime account identity for a raw token."""
        headers = {'Authorization': f'Bearer {access_token}'}
        async with aiohttp.ClientSession() as session:
            async with session.get(USERINFO_URL, headers=headers) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise RacetimeAPIError(
                        f"racetime userinfo request failed ({resp.status}): {text}"
                    )
                import json as _json
                try:
                    payload = _json.loads(text)
                except ValueError as e:
                    raise RacetimeAPIError(f"racetime API returned non-JSON: {text[:200]}") from e
        user_id = _opt_str(payload.get('id'))
        if not user_id:
            raise RacetimeAPIError(f"racetime userinfo response missing id: {payload}")
        return {
            'user_id': user_id,
            'username': payload.get('name'),
        }


# ----------------------------------------------------------------------
# Mock client (MOCK_RACETIME) — a deterministic canned identity so local dev
# can click through link/unlink without a real OAuth app.
# ----------------------------------------------------------------------
_MOCK_IDENTITIES = [
    {'user_id': 'mockrt0001', 'username': 'MockRacerOne'},
    {'user_id': 'mockrt0002', 'username': 'MockRacerTwo'},
    {'user_id': 'mockrt0003', 'username': 'MockRacerThree'},
    {'user_id': 'mockrt0004', 'username': 'MockRacerFour'},
]


class MockRacetimeClient(RacetimeClient):
    """Canned client used when MOCK_RACETIME is enabled."""

    def __init__(self, *args, **kwargs):  # noqa: D401 - signature compat
        super().__init__('mock', 'mock')

    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        return {'access_token': 'mock-access', 'token_type': 'bearer', 'expires_in': 36000}

    async def get_me(self, access_token: str) -> Dict[str, Any]:
        # Which canned identity the next link binds to, chosen via env hint so
        # distinct dev users can link to distinct racetime identities.
        idx = int(os.environ.get('MOCK_RACETIME_IDENTITY', '1'))
        return dict(_MOCK_IDENTITIES[(idx - 1) % len(_MOCK_IDENTITIES)])
