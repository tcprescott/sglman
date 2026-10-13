from urllib.parse import parse_qs, urlsplit

import pytest

from application.utils.twitch_embed import parent_hostname, player_url, twitch_channel


@pytest.mark.parametrize('url, channel', [
    ('https://twitch.tv/wizzrobe', 'wizzrobe'),
    ('https://www.twitch.tv/Wizzrobe2/', 'wizzrobe2'),
    ('http://m.twitch.tv/speed_gaming?referrer=x', 'speed_gaming'),
    ('  https://twitch.tv/wizzrobe3  ', 'wizzrobe3'),
])
def test_channel_from_twitch_links(url, channel):
    assert twitch_channel(url) == channel


@pytest.mark.parametrize('url', [
    None,
    '',
    'twitch.tv/wizzrobe',
    'javascript:alert(1)//twitch.tv/x',
    'https://youtube.com/@wizzrobe',
    'https://twitch.tv.evil.example/wizzrobe',
    'https://twitch.tv/',
    'https://twitch.tv/videos/12345',
    'https://twitch.tv/directory',
    'https://twitch.tv/wizzrobe/clip/abc',
    'https://twitch.tv/bad-name',
    'https://twitch.tv/' + 'a' * 26,
])
def test_non_channel_links_are_not_embedded(url):
    assert twitch_channel(url) is None


@pytest.mark.parametrize('host, parent', [
    ('wizzrobe.gg', 'wizzrobe.gg'),
    ('localhost:8080', 'localhost'),
    ('sgl.example.com:443', 'sgl.example.com'),
    (None, None),
    ('', None),
])
def test_parent_drops_the_port(host, parent):
    assert parent_hostname(host) == parent


def test_player_url_names_channel_and_parent_and_starts_muted():
    parts = urlsplit(player_url('wizzrobe', 'wizzrobe.gg'))
    assert (parts.scheme, parts.netloc) == ('https', 'player.twitch.tv')
    assert parse_qs(parts.query) == {
        'channel': ['wizzrobe'], 'parent': ['wizzrobe.gg'], 'autoplay': ['true'], 'muted': ['true'],
    }
