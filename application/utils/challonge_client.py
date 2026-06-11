"""Challonge API v2.1 transport client.

A thin async ``aiohttp`` wrapper over the Challonge v2.1 (JSON:API) endpoints
we need, plus the OAuth token exchange/refresh. There is no mature Python
library for v2.1, so this lives here and is deliberately small.

The client returns **normalized** Python dicts so the service layer never has
to know the JSON:API wire shape:

    me               -> {'user_id', 'username'}
    tournament       -> {'id', 'name', 'url', 'state'}
    participant      -> {'participant_id', 'name', 'challonge_user_id', 'username'}
    match            -> {'match_id', 'state', 'round',
                         'player1_participant_id', 'player2_participant_id',
                         'winner_participant_id'}

Authenticated service calls obtain a bearer token via a ``token_provider``
callback (``async (force_refresh: bool = False) -> str``) so the client can
transparently refresh-on-401 and retry once. OAuth helpers
(:meth:`exchange_code`, :meth:`refresh`, :meth:`get_me`) take explicit tokens
because they run outside an established connection (e.g. the player-link
callback, which never stores a token).
"""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import quote

import aiohttp

AUTHORIZE_URL = 'https://api.challonge.com/oauth/authorize'
TOKEN_URL = 'https://api.challonge.com/oauth/token'
BASE_URL = 'https://api.challonge.com/v2.1'

TokenProvider = Callable[..., Awaitable[str]]


class ChallongeAPIError(Exception):
    """Raised when the Challonge API returns an error or unexpected payload."""


def build_authorize_url(client_id: str, redirect_uri: str, scope: str, state: str) -> str:
    """Return the Challonge OAuth authorize URL to redirect the browser to."""
    return (
        f"{AUTHORIZE_URL}"
        f"?client_id={quote(client_id, safe='')}"
        f"&redirect_uri={quote(redirect_uri, safe='')}"
        f"&response_type=code"
        f"&scope={quote(scope, safe='')}"
        f"&state={quote(state, safe='')}"
    )


def _attr(resource: Dict[str, Any], *keys: str) -> Optional[Any]:
    """Pull the first present key from a JSON:API resource's ``attributes``.

    v2.1 attribute names are not always documented, so we try a few synonyms
    and fall back to None rather than KeyError.
    """
    attrs = resource.get('attributes') or {}
    for key in keys:
        if key in attrs and attrs[key] is not None:
            return attrs[key]
    return None


def _rel_id(resource: Dict[str, Any], rel: str) -> Optional[str]:
    """Pull a to-one relationship's id from a JSON:API resource."""
    rels = resource.get('relationships') or {}
    data = (rels.get(rel) or {}).get('data')
    if isinstance(data, dict) and data.get('id') is not None:
        return str(data['id'])
    return None


def _normalize_participant(resource: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'participant_id': str(resource.get('id')),
        'name': _attr(resource, 'name', 'display_name'),
        'challonge_user_id': _opt_str(_attr(resource, 'challonge_user_id', 'user_id')),
        'username': _attr(resource, 'challonge_username', 'username'),
    }


def _normalize_match(resource: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'match_id': str(resource.get('id')),
        'state': _attr(resource, 'state'),
        'round': _attr(resource, 'round'),
        'player1_participant_id': _opt_str(
            _attr(resource, 'player1_id') or _rel_id(resource, 'player1')
        ),
        'player2_participant_id': _opt_str(
            _attr(resource, 'player2_id') or _rel_id(resource, 'player2')
        ),
        'winner_participant_id': _opt_str(
            _attr(resource, 'winner_id') or _rel_id(resource, 'winner')
        ),
    }


def _opt_str(value: Any) -> Optional[str]:
    return None if value is None else str(value)


class ChallongeClient:
    """Async Challonge v2.1 client."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_provider: Optional[TokenProvider] = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token_provider = token_provider

    # ------------------------------------------------------------------
    # OAuth (explicit-token / no-connection context)
    # ------------------------------------------------------------------
    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange an authorization code for a token payload."""
        return await self._token_request({
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': redirect_uri,
            'code': code,
        })

    async def refresh(self, refresh_token: str) -> Dict[str, Any]:
        """Exchange a refresh token for a new token payload."""
        return await self._token_request({
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': refresh_token,
        })

    async def _token_request(self, data: Dict[str, str]) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.post(TOKEN_URL, data=data) as resp:
                payload = await resp.json()
                if resp.status >= 400:
                    raise ChallongeAPIError(
                        f"Challonge token request failed ({resp.status}): {payload}"
                    )
                return payload

    async def get_me(self, access_token: str) -> Dict[str, Any]:
        """Fetch the authenticated Challonge account identity for a raw token."""
        data = await self._raw_get('/me.json', access_token)
        resource = data.get('data') or {}
        return {
            'user_id': _opt_str(resource.get('id') or _attr(resource, 'id')),
            'username': _attr(resource, 'username', 'name'),
        }

    # ------------------------------------------------------------------
    # Authenticated service calls (token via token_provider)
    # ------------------------------------------------------------------
    async def get_tournament(self, tournament_id: str) -> Dict[str, Any]:
        data = await self._authed_request('GET', f'/tournaments/{tournament_id}.json')
        resource = data.get('data') or {}
        return {
            'id': str(resource.get('id')),
            'name': _attr(resource, 'name'),
            'url': _attr(resource, 'full_challonge_url', 'url'),
            'state': _attr(resource, 'state'),
        }

    async def list_participants(self, tournament_id: str) -> List[Dict[str, Any]]:
        data = await self._authed_request('GET', f'/tournaments/{tournament_id}/participants.json')
        return [_normalize_participant(r) for r in (data.get('data') or [])]

    async def list_matches(self, tournament_id: str) -> List[Dict[str, Any]]:
        data = await self._authed_request('GET', f'/tournaments/{tournament_id}/matches.json')
        return [_normalize_match(r) for r in (data.get('data') or [])]

    async def update_match(
        self,
        tournament_id: str,
        match_id: str,
        winner_participant_id: str,
        loser_participant_id: str,
        winner_score: str = '1',
        loser_score: str = '0',
    ) -> None:
        """Report a match result. The winner is flagged ``advancing: true``."""
        body = {
            'data': {
                'type': 'Match',
                'attributes': {
                    'match': [
                        {
                            'participant_id': str(winner_participant_id),
                            'score_set': str(winner_score),
                            'advancing': True,
                        },
                        {
                            'participant_id': str(loser_participant_id),
                            'score_set': str(loser_score),
                            'advancing': False,
                        },
                    ]
                },
            }
        }
        await self._authed_request(
            'PUT', f'/tournaments/{tournament_id}/matches/{match_id}.json', json=body,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _headers(self, token: str) -> Dict[str, str]:
        return {
            'Content-Type': 'application/vnd.api+json',
            'Accept': 'application/json',
            'Authorization-Type': 'v2',
            'Authorization': f'Bearer {token}',
        }

    async def _raw_get(self, path: str, token: str) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.get(BASE_URL + path, headers=self._headers(token)) as resp:
                return await self._parse(resp)

    async def _authed_request(
        self, method: str, path: str, *, json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self._token_provider is None:
            raise ChallongeAPIError('No token provider configured for authenticated calls')
        token = await self._token_provider()
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method, BASE_URL + path, headers=self._headers(token), json=json,
            ) as resp:
                if resp.status == 401:
                    # Token may have expired between refresh checks — force one refresh + retry.
                    token = await self._token_provider(force_refresh=True)
                    async with session.request(
                        method, BASE_URL + path, headers=self._headers(token), json=json,
                    ) as retry:
                        return await self._parse(retry)
                return await self._parse(resp)

    @staticmethod
    async def _parse(resp: aiohttp.ClientResponse) -> Dict[str, Any]:
        text = await resp.text()
        if resp.status >= 400:
            raise ChallongeAPIError(f"Challonge API error ({resp.status}): {text}")
        if not text:
            return {}
        import json as _json
        try:
            return _json.loads(text)
        except ValueError as e:
            raise ChallongeAPIError(f"Challonge API returned non-JSON: {text[:200]}") from e


# ----------------------------------------------------------------------
# Mock client (MOCK_CHALLONGE) — a tiny canned 4-player single-elim bracket
# so local dev can click through connect/link/sync/schedule without a real app.
# ----------------------------------------------------------------------
_MOCK_PARTICIPANTS = [
    {'participant_id': '9001', 'name': 'MockPlayerOne', 'challonge_user_id': '1001', 'username': 'mockone'},
    {'participant_id': '9002', 'name': 'MockPlayerTwo', 'challonge_user_id': '1002', 'username': 'mocktwo'},
    {'participant_id': '9003', 'name': 'MockPlayerThree', 'challonge_user_id': '1003', 'username': 'mockthree'},
    {'participant_id': '9004', 'name': 'MockPlayerFour', 'challonge_user_id': '1004', 'username': 'mockfour'},
]
_MOCK_MATCHES = [
    {'match_id': '8001', 'state': 'open', 'round': 1, 'player1_participant_id': '9001',
     'player2_participant_id': '9002', 'winner_participant_id': None},
    {'match_id': '8002', 'state': 'open', 'round': 1, 'player1_participant_id': '9003',
     'player2_participant_id': '9004', 'winner_participant_id': None},
    {'match_id': '8003', 'state': 'pending', 'round': 2, 'player1_participant_id': None,
     'player2_participant_id': None, 'winner_participant_id': None},
]


class MockChallongeClient(ChallongeClient):
    """Canned client used when MOCK_CHALLONGE is enabled."""

    def __init__(self, *args, **kwargs):  # noqa: D401 - signature compat
        super().__init__('mock', 'mock', kwargs.get('token_provider'))

    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        return {'access_token': 'mock-access', 'refresh_token': 'mock-refresh', 'expires_in': 604800,
                'scope': 'me tournaments:read matches:read matches:write participants:read'}

    async def refresh(self, refresh_token: str) -> Dict[str, Any]:
        return await self.exchange_code('mock', 'mock')

    async def get_me(self, access_token: str) -> Dict[str, Any]:
        # Deterministic per-call identity so each linking dev user maps to a
        # distinct mock participant by their numeric position is not possible;
        # use an env hint to choose which mock identity to bind.
        idx = int(os.environ.get('MOCK_CHALLONGE_IDENTITY', '1'))
        p = _MOCK_PARTICIPANTS[(idx - 1) % len(_MOCK_PARTICIPANTS)]
        return {'user_id': p['challonge_user_id'], 'username': p['username']}

    async def get_tournament(self, tournament_id: str) -> Dict[str, Any]:
        return {'id': str(tournament_id), 'name': 'Mock Challonge Tournament',
                'url': f'https://challonge.com/{tournament_id}', 'state': 'underway'}

    async def list_participants(self, tournament_id: str) -> List[Dict[str, Any]]:
        return [dict(p) for p in _MOCK_PARTICIPANTS]

    async def list_matches(self, tournament_id: str) -> List[Dict[str, Any]]:
        return [dict(m) for m in _MOCK_MATCHES]

    async def update_match(self, tournament_id, match_id, winner_participant_id,
                           loser_participant_id, winner_score='1', loser_score='0') -> None:
        print(f"[MOCK Challonge] update_match t={tournament_id} m={match_id} "
              f"winner={winner_participant_id} {winner_score}-{loser_score}")
