"""SpeedGaming schedule API transport client (PR 7).

A thin async wrapper over the one SG endpoint the ETL needs: the public schedule
feed at ``https://speedgaming.org/api/schedule``. It returns the **raw** episode
dicts SG serves; normalization into SGLMan's shape happens in the ETL service, so
this layer stays a pure transport.

``MOCK_SPEEDGAMING`` swaps in :class:`MockSpeedGamingClient`, a deterministic
scripted fake that returns canned episodes so local dev and the browser
validation loop can exercise the full ETL without hitting speedgaming.org. Like
the other mock flags it refuses to run under ``ENVIRONMENT=production``.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from application.utils.environment import is_production

SPEEDGAMING_BASE = 'https://speedgaming.org'
SCHEDULE_URL = f'{SPEEDGAMING_BASE}/api/schedule'

# A courteous cap so a misconfigured window never pulls an unbounded page.
REQUEST_TIMEOUT_SECONDS = 20


class SpeedGamingAPIError(Exception):
    """Raised when the SG API errors or returns an unexpected payload."""


def is_mock_speedgaming() -> bool:
    """Return True when MOCK_SPEEDGAMING is enabled (and not in production)."""
    enabled = os.environ.get('MOCK_SPEEDGAMING', '').strip().lower() in ('1', 'true', 'yes', 'on')
    if enabled and is_production():
        raise RuntimeError(
            'MOCK_SPEEDGAMING must not be enabled in production: it fakes the '
            'SpeedGaming schedule feed. Unset MOCK_SPEEDGAMING or change ENVIRONMENT.'
        )
    return enabled


class SpeedGamingClient:
    """Async SpeedGaming schedule client."""

    async def fetch_schedule(
        self,
        event_slug: str,
        start: datetime,
        end: datetime,
        content_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch raw episodes for an event over ``[start, end]`` (UTC datetimes).

        Returns the SG API's list of episode dicts verbatim. Raises
        :class:`SpeedGamingAPIError` on a non-2xx response or non-list payload.
        """
        params = {
            'event': event_slug,
            'from': start.isoformat(),
            'to': end.isoformat(),
        }
        if content_type:
            params['type'] = content_type
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(SCHEDULE_URL, params=params) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise SpeedGamingAPIError(
                        f"SpeedGaming schedule request failed ({resp.status}): {text[:200]}"
                    )
                import json as _json
                try:
                    payload = _json.loads(text)
                except ValueError as e:
                    raise SpeedGamingAPIError(
                        f"SpeedGaming API returned non-JSON: {text[:200]}"
                    ) from e
        if not isinstance(payload, list):
            raise SpeedGamingAPIError(
                f"SpeedGaming schedule payload was not a list: {type(payload).__name__}"
            )
        return payload


class MockSpeedGamingClient(SpeedGamingClient):
    """Scripted client used when MOCK_SPEEDGAMING is enabled.

    Returns deterministic canned episodes so the ETL, read-only guard, and admin
    observability can all be exercised end-to-end without the live SG API. The
    episodes are shaped like the real feed (``id``, ``when``, ``match1.players``
    with ``discordId``/``discordTag``, channel + crew metadata).
    """

    def __init__(self, episodes: Optional[List[Dict[str, Any]]] = None) -> None:
        self._episodes = episodes if episodes is not None else _MOCK_EPISODES

    async def fetch_schedule(
        self,
        event_slug: str,
        start: datetime,
        end: datetime,
        content_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # Return a deep-ish copy so a caller mutating the transform input can't
        # corrupt the canned fixtures across polls.
        import copy
        return [copy.deepcopy(ep) for ep in self._episodes]


def get_speedgaming_client() -> SpeedGamingClient:
    """Return the live or mock SG client per ``MOCK_SPEEDGAMING``."""
    if is_mock_speedgaming():
        return MockSpeedGamingClient()
    return SpeedGamingClient()


# ----------------------------------------------------------------------
# Canned fixtures for MOCK_SPEEDGAMING. One resolvable player (real discord id),
# one resolvable-by-username player, and one unmatched player (becomes a
# placeholder). ``when`` is a fixed future-ish instant; the ETL re-parses it.
# ----------------------------------------------------------------------
_MOCK_EPISODES: List[Dict[str, Any]] = [
    {
        'id': 900001,
        'title': 'Mock Bracket — Round 1',
        'event': {'slug': 'mockevent', 'name': 'Mock Event'},
        'when': '2026-07-20T18:00:00+00:00',
        'length': 90,
        'approved': True,
        'match1': {
            'title': 'Round 1',
            'players': [
                {'id': 5001, 'displayName': 'PlayerOne', 'discordId': '111111111111111111',
                 'discordTag': 'playerone', 'approved': True},
                {'id': 5002, 'displayName': 'sg_only_user', 'discordId': None,
                 'discordTag': 'sgonlyuser', 'approved': True},
            ],
        },
        'channels': [{'name': 'SpeedGaming', 'slug': 'speedgaming'}],
        'commentators': [
            {'id': 6001, 'displayName': 'CasterOne', 'discordId': None, 'discordTag': 'casterone',
             'approved': True},
        ],
        'trackers': [],
    },
    {
        'id': 900002,
        'title': 'Mock Bracket — Round 2',
        'event': {'slug': 'mockevent', 'name': 'Mock Event'},
        'when': '2026-07-21T20:30:00+00:00',
        'length': 90,
        'approved': True,
        'match1': {
            'title': 'Round 2',
            'players': [
                {'id': 5003, 'displayName': 'PlayerTwo', 'discordId': '222222222222222222',
                 'discordTag': 'playertwo', 'approved': True},
                {'id': 5001, 'displayName': 'PlayerOne', 'discordId': '111111111111111111',
                 'discordTag': 'playerone', 'approved': True},
            ],
        },
        'channels': [{'name': 'SpeedGaming', 'slug': 'speedgaming'}],
        'commentators': [],
        'trackers': [],
    },
]
