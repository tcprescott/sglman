"""The live racetime ``startrace`` client, against a faked aiohttp session.

What it must get right: the bot token grant, a goal racetime knows sent as
``goal`` and anything else as ``custom_goal``, booleans as the strings racetime
parses, and the room's slug taken from racetime's ``Location`` header.
"""

import pytest

from application.utils.clients import racetime_rooms_client
from application.utils.clients.racetime_client import RacetimeAPIError
from application.utils.clients.racetime_rooms_client import (
    RaceRoomSettings,
    RacetimeRoomsClient,
    slug_from_location,
)


class _Resp:
    def __init__(self, status=200, json=None, headers=None, text=''):
        self.status = status
        self._json = json or {}
        self.headers = headers or {}
        self._text = text

    async def json(self):
        return self._json

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def _respond(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.routes[(method, url)]

    def post(self, url, **kwargs):
        return self._respond('POST', url, **kwargs)

    def get(self, url, **kwargs):
        return self._respond('GET', url, **kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def session(monkeypatch):
    import aiohttp

    racetime_rooms_client._tokens.clear()
    fake = _Session({
        ('POST', 'https://racetime.gg/o/token'): _Resp(json={
            'access_token': 'tok', 'expires_in': 36000,
        }),
        ('GET', 'https://racetime.gg/alttpr/data'): _Resp(json={
            'goals': ['Beat the game', 'All Dungeons'],
        }),
        ('POST', 'https://racetime.gg/o/alttpr/startrace'): _Resp(
            status=201, headers={'Location': '/alttpr/clever-link-1234'},
        ),
    })
    monkeypatch.setattr(aiohttp, 'ClientSession', lambda **kwargs: fake)
    yield fake
    racetime_rooms_client._tokens.clear()


async def _start(goal='Beat the game', **settings):
    return await RacetimeRoomsClient().start_race(
        category='alttpr', client_id='cid', client_secret='secret',
        settings=RaceRoomSettings(goal=goal, **settings),
    )


async def test_opens_a_room_and_returns_racetimes_slug(session):
    assert await _start(invitational=True, start_delay=30) == 'alttpr/clever-link-1234'

    method, url, kwargs = session.calls[-1]
    assert kwargs['headers'] == {'Authorization': 'Bearer tok'}
    form = kwargs['data']
    assert form['goal'] == 'Beat the game' and 'custom_goal' not in form
    assert form['invitational'] == 'true' and form['unlisted'] == 'false'
    assert form['start_delay'] == '30'


async def test_an_unknown_goal_goes_as_a_custom_goal(session):
    await _start(goal='Swordless 100%')

    form = session.calls[-1][2]['data']
    assert form['custom_goal'] == 'Swordless 100%' and 'goal' not in form


async def test_the_bot_token_is_reused_across_rooms(session):
    await _start()
    await _start()

    grants = [c for c in session.calls if c[1] == 'https://racetime.gg/o/token']
    assert len(grants) == 1


async def test_a_refusal_carries_racetimes_reason(session):
    session.routes[('POST', 'https://racetime.gg/o/alttpr/startrace')] = _Resp(
        status=400, text='{"errors": ["Custom goals are not allowed"]}',
    )
    with pytest.raises(RacetimeAPIError, match='Custom goals are not allowed'):
        await _start(goal='Something else')


async def test_rejected_credentials_never_reach_startrace(session):
    session.routes[('POST', 'https://racetime.gg/o/token')] = _Resp(status=401)
    with pytest.raises(RacetimeAPIError, match='rejected the bot credentials'):
        await _start()
    assert not any(c[1].endswith('/startrace') for c in session.calls)


@pytest.mark.parametrize('location, slug', [
    ('/alttpr/clever-link-1234', 'alttpr/clever-link-1234'),
    ('https://racetime.gg/alttpr/clever-link-1234', 'alttpr/clever-link-1234'),
])
def test_slug_from_location(location, slug):
    assert slug_from_location(location) == slug


@pytest.mark.parametrize('location', [None, '', '/alttpr', '/alttpr/a/b'])
def test_an_unexpected_location_is_an_error(location):
    with pytest.raises(RacetimeAPIError):
        slug_from_location(location)


def test_profile_settings_carry_over():
    class _Profile:
        invitational = True
        unlisted = True
        auto_start = False
        allow_comments = False
        allow_midrace_chat = False
        allow_non_entrant_chat = False
        chat_message_delay = 5
        start_delay = 20
        time_limit = 12
        streaming_required = True

    form = RaceRoomSettings.from_profile(_Profile(), goal='g').form([])
    assert form['auto_start'] == 'false' and form['streaming_required'] == 'true'
    assert form['chat_message_delay'] == '5' and form['time_limit'] == '12'


async def test_an_html_error_page_is_not_shown_as_the_reason(session):
    session.routes[('POST', 'https://racetime.gg/o/alttpr/startrace')] = _Resp(
        status=502, text='<html><body>Bad gateway</body></html>',
    )
    with pytest.raises(RacetimeAPIError) as err:
        await _start()
    assert '<html>' not in str(err.value) and '(502)' in str(err.value)
