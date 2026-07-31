"""Tests for the SpeedGaming transport client's handling of the live API's quirks.

SG publishes no schema; these pin the two behaviours reconstructed from
SahasrahBot's production use of the feed — a JSON error object served with a 200,
and canned fixtures shaped like the real payload.
"""

import pytest

from application.utils.clients.speedgaming_client import (
    _MOCK_EPISODES,
    MockSpeedGamingClient,
    SpeedGamingAPIError,
    _validate_schedule_payload,
)


def test_error_object_raises_with_sg_message():
    # An unknown event slug answers 200 with a JSON object, not a list.
    with pytest.raises(SpeedGamingAPIError) as exc:
        _validate_schedule_payload({'error': 'Failed to find event nosuchevent.'}, 'nosuchevent')
    assert 'Failed to find event nosuchevent.' in str(exc.value)
    assert 'nosuchevent' in str(exc.value)


def test_empty_schedule_is_not_an_error():
    assert _validate_schedule_payload([], 'ev') == []


def test_non_list_payload_raises():
    with pytest.raises(SpeedGamingAPIError):
        _validate_schedule_payload({'unexpected': True}, 'ev')


@pytest.mark.parametrize('episode', _MOCK_EPISODES)
def test_mock_fixtures_match_the_live_episode_shape(episode):
    """Every canned episode carries the fields the real feed serves.

    Guards against the fixtures drifting back into a simplified shape that lets
    consumers rely on fields SG does not actually send.
    """
    assert 'title' not in episode, 'SG has no episode-level title; it lives at match1.title'
    for key in ('id', 'when', 'whenCountdown', 'approved', 'event', 'match1',
                'channels', 'commentators', 'trackers', 'broadcasters'):
        assert key in episode, f'missing {key}'
    assert set(episode['event']) >= {'slug', 'name', 'shortName'}
    assert isinstance(episode['match1']['title'], str)
    for player in episode['match1']['players']:
        assert set(player) >= {'id', 'displayName', 'discordId', 'discordTag',
                               'approved', 'publicStream', 'streamingFrom'}
    for role in ('commentators', 'trackers', 'broadcasters'):
        for member in episode[role]:
            assert set(member) >= {'id', 'displayName', 'discordId', 'discordTag',
                                   'approved', 'language'}


def test_mock_fixtures_cover_the_states_the_etl_branches_on():
    assert any(e['approved'] is False for e in _MOCK_EPISODES), 'need an unapproved episode'
    assert any(e['match1']['title'] == '' for e in _MOCK_EPISODES), 'need a TBD matchup'
    assert any(len(e['match1']['players']) > 2 for e in _MOCK_EPISODES), 'need a >2-player match'
    players = [p for e in _MOCK_EPISODES for p in e['match1']['players']]
    assert any(p['discordId'] for p in players), 'need a discord-resolvable player'
    assert any(not p['discordId'] and p['discordTag'] for p in players), 'need a tag-only player'
    assert any(not p['discordId'] and not p['discordTag'] for p in players), 'need a placeholder'


async def test_mock_client_returns_deep_copies():
    client = MockSpeedGamingClient()
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    first = await client.fetch_schedule('mockevent', now, now)
    first[0]['match1']['players'][0]['displayName'] = 'mutated'
    second = await client.fetch_schedule('mockevent', now, now)
    assert second[0]['match1']['players'][0]['displayName'] != 'mutated'
