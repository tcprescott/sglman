"""Matcherino transport client for event check-in.

Matcherino publishes no API. The two endpoints here are the ones its own web
app calls, used with Matcherino's go-ahead but **without** any support promise
from them — they may change or disappear without notice. Everything in this
module is written for that: the parse is strict about the two fields check-in
cannot work without (``userId``, ``displayName``) and raises
:class:`MatcherinoAPIError` rather than guessing, and the sync that consumes it
treats any failure as "keep the roster we have" (see ``CheckInService``).

Wire shape, captured from the live API:

* ``GET /__api/bounties/participants?bountyId=&page=&pageSize=`` answers
  ``{"status": 200, "body": {"pageCount", "itemCount", "contents": [...]}}``.
  Pages are zero-indexed. An unknown bounty is **not** an error: it is
  ``200`` with ``contents: null`` and ``itemCount: 0``, indistinguishable from
  an empty bounty.
* ``GET /__api/bounties/findById?id=`` answers ``{"status": 200, "body":
  {"id", "title", ...}}``.
* Failures come back as ``{"status": 500, "error": {"message": ...}}``, with a
  matching HTTP status.

Each participant carries the account the person signed in to Matcherino with
(``authProvider`` + ``authId``). For ``discord`` the id is the Discord snowflake
and for ``twitch`` it is the Twitch user id, which is what makes most matches
exact. ``socials`` sometimes lists a linked Twitch login as well.

``MOCK_MATCHERINO`` swaps in :class:`MockMatcherinoClient`, which serves canned
participants so local dev and the browser loop never call Matcherino. Like the
other mock flags it refuses to run under ``ENVIRONMENT=production``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from application.utils.environment import env_flag, is_production

MATCHERINO_API = 'https://api.matcherino.com/__api'
PARTICIPANTS_URL = f'{MATCHERINO_API}/bounties/participants'
BOUNTY_URL = f'{MATCHERINO_API}/bounties/findById'

PAGE_SIZE = 500
# A bounty bigger than this many pages is far outside anything check-in is for;
# the cap stops a misbehaving pageCount from looping forever.
MAX_PAGES = 20
REQUEST_TIMEOUT_SECONDS = 20
USER_AGENT = 'Wizzrobe event check-in'


class MatcherinoAPIError(Exception):
    """Matcherino errored, or served a payload this module does not recognise."""


def is_mock_matcherino() -> bool:
    """Return True when MOCK_MATCHERINO is enabled (and not in production)."""
    enabled = env_flag('MOCK_MATCHERINO')
    if enabled and is_production():
        raise RuntimeError(
            'MOCK_MATCHERINO must not be enabled in production: it fakes the '
            'Matcherino registration list. Unset MOCK_MATCHERINO or change ENVIRONMENT.'
        )
    return enabled


@dataclass(frozen=True)
class MatcherinoParticipant:
    """One bounty participant, with the raw object kept beside the parsed fields.

    ``raw`` is what gets stored as ``CheckInEntrant.source_data``. A field
    Matcherino starts serving later is read from there, not by widening this
    parse before anyone needs it.
    """

    user_id: str
    display_name: str
    auth_provider: Optional[str] = None
    auth_id: Optional[str] = None
    avatar_url: Optional[str] = None
    twitch_login: Optional[str] = None
    registered_at: Optional[datetime] = None
    raw: Dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def handle(self) -> str:
        """The ``name#id`` form ``User.matcherino_username`` stores."""
        return f'{self.display_name}#{self.user_id}'


@dataclass(frozen=True)
class MatcherinoBounty:
    id: int
    title: str


def _opt_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_time(value: Any) -> Optional[datetime]:
    text = _opt_str(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _twitch_login(raw: Dict[str, Any]) -> Optional[str]:
    for social in raw.get('socials') or []:
        if isinstance(social, dict) and social.get('provider') == 'twitch':
            login = _opt_str(social.get('name'))
            if login:
                return login.lower()
    return None


def parse_participant(raw: Any) -> MatcherinoParticipant:
    """Parse one participant object, or raise if the shape has changed."""
    if not isinstance(raw, dict):
        raise MatcherinoAPIError(f'Matcherino participant was not an object: {type(raw).__name__}')
    user_id = _opt_str(raw.get('userId'))
    display_name = _opt_str(raw.get('displayName'))
    if user_id is None or display_name is None:
        raise MatcherinoAPIError(
            'Matcherino participant is missing userId or displayName; '
            'the API shape may have changed.'
        )
    return MatcherinoParticipant(
        user_id=user_id,
        display_name=display_name,
        auth_provider=(_opt_str(raw.get('authProvider')) or '').lower() or None,
        auth_id=_opt_str(raw.get('authId')),
        avatar_url=_opt_str(raw.get('avatar')),
        twitch_login=_twitch_login(raw),
        registered_at=_parse_time(raw.get('addedAt')),
        raw=raw,
    )


def _unwrap(payload: Any, what: str) -> Dict[str, Any]:
    """Return the envelope's ``body``, or raise with Matcherino's own message."""
    if not isinstance(payload, dict):
        raise MatcherinoAPIError(f'Matcherino {what} response was not an object.')
    error = payload.get('error')
    if error:
        message = error.get('message') if isinstance(error, dict) else str(error)
        raise MatcherinoAPIError(f'Matcherino rejected the {what} request: {message or "unknown error"}')
    body = payload.get('body')
    if not isinstance(body, dict):
        raise MatcherinoAPIError(f'Matcherino {what} response had no body.')
    return body


class MatcherinoClient:
    """Async client for the two Matcherino endpoints check-in uses."""

    async def _get(self, client: httpx.AsyncClient, url: str, params: Dict[str, Any], what: str) -> Dict[str, Any]:
        try:
            resp = await client.get(url, params=params)
        except httpx.HTTPError as e:
            raise MatcherinoAPIError(f"Couldn't reach Matcherino: {e.__class__.__name__}") from e
        try:
            payload = resp.json()
        except ValueError as e:
            raise MatcherinoAPIError(
                f'Matcherino returned non-JSON ({resp.status_code}): {resp.text[:200]}'
            ) from e
        body = _unwrap(payload, what)
        if resp.status_code >= 400:
            raise MatcherinoAPIError(f'Matcherino {what} request failed ({resp.status_code}).')
        return body

    def _session(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'},
        )

    async def fetch_participants(self, bounty_id: int) -> List[MatcherinoParticipant]:
        """Every participant in the bounty, across all pages.

        A short read is an error, not a smaller roster: the sync marks anyone
        missing from this list as withdrawn, so a page that comes back empty
        or a cap that cuts the list off must not look like people leaving.
        The count is checked against page 0's ``itemCount``, by distinct id
        (offset paging can repeat a row when someone registers mid-read).
        """
        participants: List[MatcherinoParticipant] = []
        expected: Optional[int] = None
        async with self._session() as client:
            page = 0
            while True:
                body = await self._get(
                    client, PARTICIPANTS_URL,
                    {'bountyId': bounty_id, 'page': page, 'pageSize': PAGE_SIZE},
                    'participants',
                )
                contents = body.get('contents') or []
                if not isinstance(contents, list):
                    raise MatcherinoAPIError('Matcherino participants were not a list.')
                participants.extend(parse_participant(raw) for raw in contents)
                if expected is None:
                    expected = int(body.get('itemCount') or 0)
                page += 1
                page_count = body.get('pageCount') or 0
                if page >= page_count:
                    break
                if page >= MAX_PAGES:
                    raise MatcherinoAPIError(
                        f'Matcherino bounty {bounty_id} has more than {MAX_PAGES} pages of participants.'
                    )
        distinct = len({p.user_id for p in participants})
        if expected and distinct < expected:
            raise MatcherinoAPIError(
                f'Matcherino listed {expected} participants but served {distinct}; '
                'treating the read as incomplete.'
            )
        return participants

    async def fetch_bounty(self, bounty_id: int) -> MatcherinoBounty:
        async with self._session() as client:
            body = await self._get(client, BOUNTY_URL, {'id': bounty_id}, 'bounty')
        title = _opt_str(body.get('title'))
        if body.get('id') is None or title is None:
            raise MatcherinoAPIError(f'Matcherino has no bounty {bounty_id}.')
        return MatcherinoBounty(id=int(body['id']), title=title)


class MockMatcherinoClient(MatcherinoClient):
    """Canned client for ``MOCK_MATCHERINO`` and tests.

    Serves the same participant objects for any bounty id, shaped like the live
    feed, so the full sync and matching path runs offline. Pass ``participants``
    to script a different roster (tests do).
    """

    def __init__(
        self,
        participants: Optional[List[Dict[str, Any]]] = None,
        title: str = 'Mock Matcherino Event',
    ) -> None:
        self._participants = participants if participants is not None else MOCK_PARTICIPANTS
        self._title = title

    async def fetch_participants(self, bounty_id: int) -> List[MatcherinoParticipant]:
        return [parse_participant(copy.deepcopy(raw)) for raw in self._participants]

    async def fetch_bounty(self, bounty_id: int) -> MatcherinoBounty:
        return MatcherinoBounty(id=bounty_id, title=self._title)


def get_matcherino_client() -> MatcherinoClient:
    """Return the live or mock client per ``MOCK_MATCHERINO``."""
    if is_mock_matcherino():
        return MockMatcherinoClient()
    return MatcherinoClient()


def mock_participant(
    user_id: int,
    display_name: str,
    *,
    auth_provider: str = 'gplus',
    auth_id: str = '',
    twitch_login: Optional[str] = None,
    added_at: str = '2026-09-01T12:00:00Z',
) -> Dict[str, Any]:
    """A participant object in the live feed's exact key set."""
    socials = None
    if twitch_login:
        socials = [{'avatarUrl': '', 'name': twitch_login, 'nickName': twitch_login,
                    'provider': 'twitch', 'url': ''}]
    return {
        'addedAt': added_at,
        'addedBy': 0,
        'authId': auth_id or str(10_000_000 + user_id),
        'authProvider': auth_provider,
        'avatar': '',
        'bountyId': 0,
        'displayName': display_name,
        'entryWeight': 0,
        'groupId': 1,
        'placement': 0,
        'socialMediaIdentifier': '',
        'socialProfile': {},
        'socials': socials,
        'supercellBgcolor': '',
        'supercellCharacter': '',
        'updatedAt': None,
        'userId': user_id,
    }


# The MOCK_MATCHERINO roster, which ``scripts/seed_check_in.py`` also syncs into
# the dev database, so pressing Sync in dev fetches exactly what was seeded.
# Each registrant is lined up with a seeded fixture so a real sync produces
# every link method (``tests/test_seed_coverage.py`` checks they all appear):
#
# * jemgold / blueshell / ridgeline carry the user ids from the handles the
#   payouts seed gives player_one/two/four — the handle rule;
# * DiscordRacer's authId is racer_06's derived fixture Discord id
#   (``seed_support.fixture_discord_id``; a seed test pins the value) — Discord;
# * MockTwitch's authId is the Twitch id the seed puts on racer_07 — Twitch id;
# * TwitchLoginFan lists the Twitch login the seed puts on racer_08 — login;
# * Racer Five's userId is the Matcherino id the seed puts on racer_05 — the
#   remembered-account rule;
# * Player Three is linked by hand in the seed; the last two stay unlinked.
MOCK_DISCORD_RACER_ID = '100000000073811948'
MOCK_TWITCH_RACER_ID = '555000222'
MOCK_TWITCH_RACER_LOGIN = 'racer8live'
MOCK_REMEMBERED_ID = 900005

MOCK_PARTICIPANTS: List[Dict[str, Any]] = [
    mock_participant(100234, 'jemgold', auth_provider='discord', auth_id='100000000000000001',
                     added_at='2026-08-02T18:00:00Z'),
    mock_participant(204871, 'blueshell', auth_provider='twitch', auth_id='555000111',
                     twitch_login='blueshell', added_at='2026-08-14T09:30:00Z'),
    mock_participant(309552, 'ridgeline', auth_provider='gplus', added_at='2026-09-01T12:00:00Z'),
    mock_participant(900001, 'DiscordRacer', auth_provider='discord', auth_id=MOCK_DISCORD_RACER_ID),
    mock_participant(900002, 'MockTwitch', auth_provider='twitch', auth_id=MOCK_TWITCH_RACER_ID,
                     twitch_login='mocktwitch'),
    mock_participant(900003, 'Player Three', auth_provider='gplus'),
    mock_participant(900004, 'Mock_Facebook', auth_provider='facebook'),
    mock_participant(MOCK_REMEMBERED_ID, 'Racer Five', auth_provider='gplus'),
    mock_participant(900006, 'TwitchLoginFan', auth_provider='discord', auth_id='100000000000000006',
                     twitch_login=MOCK_TWITCH_RACER_LOGIN),
    mock_participant(900007, 'Mock Google', auth_provider='gplus'),
]
