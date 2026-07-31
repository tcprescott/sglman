"""SpeedGaming schedule API transport client (PR 7).

A thin async wrapper over the one SG endpoint the ETL needs: the public schedule
feed at ``https://speedgaming.org/api/schedule``. It returns the **raw** episode
dicts SG serves; normalization into Wizzrobe's shape happens in the ETL service, so
this layer stays a pure transport.

``MOCK_SPEEDGAMING`` swaps in :class:`MockSpeedGamingClient`, a deterministic
scripted fake that returns canned episodes so local dev and the browser
validation loop can exercise the full ETL without hitting speedgaming.org. Like
the other mock flags it refuses to run under ``ENVIRONMENT=production``.

SG publishes no schema, so the wire shape encoded here is reconstructed from the
field access in SahasrahBot (github.com/tcprescott/sahasrahbot), which has
consumed this feed in production for years — see ``alttprbot/util/speedgaming.py``
and its episode consumers. Two behaviours of the live API that the naive reading
gets wrong, and that this client therefore handles explicitly:

* **JSON is served as ``Content-Type: text/html``** — never call ``resp.json()``
  without an override; we parse ``resp.text()`` instead.
* **Errors come back 200 with a JSON object** (``{"error": "..."}``), not a list
  and not a 4xx. An unknown event slug looks like a success to the transport
  unless the body is inspected.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from application.utils.environment import env_flag, is_production

SPEEDGAMING_BASE = 'https://speedgaming.org'
SCHEDULE_URL = f'{SPEEDGAMING_BASE}/api/schedule'

# A courteous cap so a misconfigured window never pulls an unbounded page.
REQUEST_TIMEOUT_SECONDS = 20


class SpeedGamingAPIError(Exception):
    """Raised when the SG API errors or returns an unexpected payload."""


def is_mock_speedgaming() -> bool:
    """Return True when MOCK_SPEEDGAMING is enabled (and not in production)."""
    enabled = env_flag('MOCK_SPEEDGAMING')
    if enabled and is_production():
        raise RuntimeError(
            'MOCK_SPEEDGAMING must not be enabled in production: it fakes the '
            'SpeedGaming schedule feed. Unset MOCK_SPEEDGAMING or change ENVIRONMENT.'
        )
    return enabled


def _validate_schedule_payload(payload: Any, event_slug: str) -> List[Dict[str, Any]]:
    """Return the episode list, or raise with SG's own error text.

    A bad event slug is answered with ``200 {"error": "..."}``, so the status
    code alone cannot distinguish "no episodes" from "no such event".
    """
    if isinstance(payload, dict) and payload.get('error'):
        raise SpeedGamingAPIError(
            f"SpeedGaming rejected the schedule request for '{event_slug}': "
            f"{payload['error']}"
        )
    if not isinstance(payload, list):
        raise SpeedGamingAPIError(
            f"SpeedGaming schedule payload was not a list: {type(payload).__name__}"
        )
    return payload


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
        return _validate_schedule_payload(payload, event_slug)


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
# Canned fixtures for MOCK_SPEEDGAMING.
#
# Shaped after the live feed as SahasrahBot reads it, so the mock exercises the
# same parsing the real API demands. Three details the previous fixtures got
# wrong, each of which hid a code path:
#
# * There is **no episode-level ``title``** — the match name lives at
#   ``match1.title``, which is ``''`` (not null, not absent) while the matchup is
#   still TBD. The ETL's ``_match_title`` fallback only runs against this shape.
# * ``when`` is accompanied by ``whenCountdown`` (the pre-show/countdown instant,
#   generally earlier than ``when``), and both carry an offset rather than 'Z'.
# * Crew are four parallel lists — ``commentators``, ``trackers``,
#   ``broadcasters``, plus the ``channels`` the episode restreams on — and each
#   member carries ``approved`` and ``language``. Signups appear unapproved
#   first, so a fixture set where everything is ``approved: True`` never sees the
#   state the crew surfaces actually have to filter.
#
# Coverage: one resolvable player (real discord id), one resolvable only by
# username, one with no Discord identity at all (becomes a placeholder), a
# three-player match, a TBD matchup, and an unapproved episode with pending crew.
# ----------------------------------------------------------------------
_MOCK_EVENT: Dict[str, Any] = {
    'slug': 'mockevent',
    'name': 'Mock Event',
    'shortName': 'Mock',
}

_MOCK_CHANNELS: List[Dict[str, Any]] = [
    {'id': 7001, 'name': 'SpeedGaming', 'slug': 'speedgaming', 'language': 'en'},
]

_MOCK_EPISODES: List[Dict[str, Any]] = [
    {
        'id': 900001,
        'event': _MOCK_EVENT,
        'when': '2026-07-20T18:00:00-04:00',
        'whenCountdown': '2026-07-20T17:45:00-04:00',
        'length': 90,
        'approved': True,
        'match1': {
            'title': 'Round 1',
            'players': [
                {'id': 5001, 'displayName': 'PlayerOne', 'discordId': '111111111111111111',
                 'discordTag': 'playerone', 'approved': True,
                 'publicStream': 'playerone_tv', 'streamingFrom': 'playerone_tv'},
                {'id': 5002, 'displayName': 'sg_only_user', 'discordId': None,
                 'discordTag': 'sgonlyuser', 'approved': True,
                 'publicStream': 'sgonlyuser', 'streamingFrom': 'sgonlyuser'},
            ],
        },
        'match2': None,
        'channels': _MOCK_CHANNELS,
        'commentators': [
            {'id': 6001, 'displayName': 'CasterOne', 'discordId': None,
             'discordTag': 'casterone', 'approved': True, 'language': 'en'},
            {'id': 6002, 'displayName': 'CasterTwo', 'discordId': None,
             'discordTag': 'castertwo', 'approved': False, 'language': 'en'},
        ],
        'trackers': [
            {'id': 6003, 'displayName': 'TrackerOne', 'discordId': None,
             'discordTag': 'trackerone', 'approved': True, 'language': 'en'},
        ],
        'broadcasters': [
            {'id': 6004, 'displayName': 'RestreamerOne', 'discordId': None,
             'discordTag': 'restreamerone', 'approved': True, 'language': 'en'},
        ],
    },
    {
        'id': 900002,
        'event': _MOCK_EVENT,
        'when': '2026-07-21T20:30:00-04:00',
        'whenCountdown': '2026-07-21T20:15:00-04:00',
        'length': 90,
        'approved': True,
        'match1': {
            'title': 'Round 2',
            'players': [
                {'id': 5003, 'displayName': 'PlayerTwo', 'discordId': '222222222222222222',
                 'discordTag': 'playertwo', 'approved': True,
                 'publicStream': 'playertwo', 'streamingFrom': 'playertwo'},
                {'id': 5001, 'displayName': 'PlayerOne', 'discordId': '111111111111111111',
                 'discordTag': 'playerone', 'approved': True,
                 'publicStream': 'playerone_tv', 'streamingFrom': 'playerone_tv'},
            ],
        },
        'match2': None,
        'channels': _MOCK_CHANNELS,
        'commentators': [],
        'trackers': [],
        'broadcasters': [],
    },
    {
        # Three-player match, still unapproved, crew signups all pending. The
        # matchup is TBD — SG serves an empty string, not null.
        'id': 900003,
        'event': _MOCK_EVENT,
        'when': '2026-07-22T19:00:00-04:00',
        'whenCountdown': '2026-07-22T18:45:00-04:00',
        'length': 120,
        'approved': False,
        'match1': {
            'title': '',
            'players': [
                {'id': 5004, 'displayName': 'PlayerThree', 'discordId': None,
                 'discordTag': None, 'approved': False,
                 'publicStream': None, 'streamingFrom': None},
                {'id': 5005, 'displayName': 'PlayerFour', 'discordId': None,
                 'discordTag': 'playerfour', 'approved': False,
                 'publicStream': 'playerfour', 'streamingFrom': 'playerfour'},
                {'id': 5006, 'displayName': 'PlayerFive', 'discordId': None,
                 'discordTag': 'playerfive', 'approved': False,
                 'publicStream': 'playerfive', 'streamingFrom': 'playerfive'},
            ],
        },
        'match2': None,
        'channels': [],
        'commentators': [
            {'id': 6005, 'displayName': 'CasterThree', 'discordId': None,
             'discordTag': 'casterthree', 'approved': False, 'language': 'en'},
        ],
        'trackers': [],
        'broadcasters': [],
    },
]
