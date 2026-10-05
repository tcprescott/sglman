"""The Matcherino client's reading of the live wire shape, served through MockTransport."""

import httpx
import pytest

from application.utils.clients import matcherino_client as mc
from application.utils.clients.matcherino_client import (
    MatcherinoAPIError,
    MatcherinoClient,
    mock_participant,
    parse_participant,
)

LIVE_KEYS = {
    'addedAt', 'addedBy', 'authId', 'authProvider', 'avatar', 'bountyId', 'displayName',
    'entryWeight', 'groupId', 'placement', 'socialMediaIdentifier', 'socialProfile',
    'socials', 'supercellBgcolor', 'supercellCharacter', 'updatedAt', 'userId',
}


def _client(monkeypatch, handler) -> MatcherinoClient:
    client = MatcherinoClient()
    monkeypatch.setattr(
        client, '_session',
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return client


def _page(contents, page_count, status=200, item_count=None):
    return {'status': status, 'body': {
        'query': {}, 'links': {}, 'pageCount': page_count,
        'itemCount': len(contents or []) if item_count is None else item_count, 'contents': contents,
    }}


def test_the_mock_fixture_matches_the_live_key_set():
    assert set(mock_participant(1, 'x')) == LIVE_KEYS
    for raw in mc.MOCK_PARTICIPANTS:
        assert set(raw) == LIVE_KEYS


def test_a_participant_parses_identity_and_keeps_the_raw_object():
    raw = mock_participant(7, 'LoginFan', auth_provider='Discord', auth_id='300000000000000020',
                           twitch_login='LoginPerson42', added_at='2026-09-28T13:15:02.450024Z')
    parsed = parse_participant(raw)

    assert (parsed.user_id, parsed.display_name, parsed.auth_provider) == ('7', 'LoginFan', 'discord')
    assert parsed.twitch_login == 'loginperson42'
    assert parsed.registered_at.tzinfo is not None
    assert parsed.handle == 'LoginFan#7'
    assert parsed.raw is raw


def test_a_participant_without_an_id_is_a_shape_change():
    raw = mock_participant(7, 'x')
    raw['userId'] = None
    with pytest.raises(MatcherinoAPIError, match='shape may have changed'):
        parse_participant(raw)


async def test_every_page_is_fetched(monkeypatch):
    pages = {
        '0': _page([mock_participant(1, 'a'), mock_participant(2, 'b')], 2, item_count=3),
        '1': _page([mock_participant(3, 'c')], 2, item_count=3),
    }
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=pages[request.url.params['page']])

    participants = await _client(monkeypatch, handler).fetch_participants(182107)

    assert [p.user_id for p in participants] == ['1', '2', '3']
    assert seen[0] == {'bountyId': '182107', 'page': '0', 'pageSize': str(mc.PAGE_SIZE)}


async def test_a_short_read_is_an_error_not_a_smaller_roster(monkeypatch):
    pages = {
        '0': {'status': 200, 'body': {'pageCount': 2, 'itemCount': 3,
                                      'contents': [mock_participant(1, 'a'), mock_participant(2, 'b')]}},
        '1': {'status': 200, 'body': {'pageCount': 2, 'itemCount': 3, 'contents': None}},
    }
    client = _client(monkeypatch, lambda r: httpx.Response(200, json=pages[r.url.params['page']]))
    with pytest.raises(MatcherinoAPIError, match='listed 3 participants but served 2'):
        await client.fetch_participants(1)


async def test_hitting_the_page_cap_is_an_error(monkeypatch):
    monkeypatch.setattr(mc, 'MAX_PAGES', 1)
    body = {'status': 200, 'body': {'pageCount': 2, 'itemCount': 1, 'contents': [mock_participant(1, 'a')]}}
    client = _client(monkeypatch, lambda r: httpx.Response(200, json=body))
    with pytest.raises(MatcherinoAPIError, match='more than 1 pages'):
        await client.fetch_participants(1)


async def test_an_unknown_bounty_reads_as_empty(monkeypatch):
    client = _client(monkeypatch, lambda r: httpx.Response(200, json=_page(None, 0)))
    assert await client.fetch_participants(999999999) == []


async def test_an_error_envelope_raises_with_matcherinos_message(monkeypatch):
    body = {'status': 500, 'error': {'message': 'Failed to parse int string'}, 'body': None}
    client = _client(monkeypatch, lambda r: httpx.Response(500, json=body))
    with pytest.raises(MatcherinoAPIError, match='Failed to parse int string'):
        await client.fetch_participants(1)


async def test_non_json_raises(monkeypatch):
    client = _client(monkeypatch, lambda r: httpx.Response(502, text='<html>bad gateway</html>'))
    with pytest.raises(MatcherinoAPIError, match='non-JSON'):
        await client.fetch_participants(1)


async def test_a_network_failure_raises(monkeypatch):
    def handler(request):
        raise httpx.ConnectError('down', request=request)

    with pytest.raises(MatcherinoAPIError, match="Couldn't reach Matcherino"):
        await _client(monkeypatch, handler).fetch_participants(1)


async def test_a_bounty_title_is_read(monkeypatch):
    body = {'status': 200, 'body': {'id': 182107, 'title': 'SpeedGaming Live 2026 Tournaments'}}
    bounty = await _client(monkeypatch, lambda r: httpx.Response(200, json=body)).fetch_bounty(182107)
    assert (bounty.id, bounty.title) == (182107, 'SpeedGaming Live 2026 Tournaments')


def test_the_mock_refuses_production(monkeypatch):
    monkeypatch.setenv('MOCK_MATCHERINO', 'true')
    monkeypatch.setattr(mc, 'is_production', lambda: True)
    with pytest.raises(RuntimeError):
        mc.is_mock_matcherino()


def test_the_mock_discord_registrant_is_racer_six():
    from scripts.seed_support import fixture_discord_id

    assert mc.MOCK_DISCORD_RACER_ID == fixture_discord_id('racer_06')
