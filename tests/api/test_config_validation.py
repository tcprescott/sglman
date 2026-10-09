"""``PUT /api/config/{key}`` holds a value to the same rules the admin page does.

It used to store any string under any key. The Discord invite is the one that
mattered: the join door opens it with ``window.open``, so a ``javascript:`` value
ran in every visitor's session who clicked Join.
"""

import pytest

from models import Role, SystemConfiguration
from tests.api_helpers import client_for, create_user_token


async def _put(app, key: str, value: str):
    _, raw = await create_user_token(username='boss', roles=[Role.STAFF], member=True)
    async with client_for(app, raw) as c:
        return await c.put(f'/api/config/{key}', json={'value': value})


@pytest.mark.parametrize('value', [
    'javascript:alert(document.cookie)',
    'https://evil.example/discord-login',
    'https://discord.gg.evil.example/abc',
])
async def test_invite_must_be_a_discord_invite(db, app, value):
    resp = await _put(app, 'discord_invite_url', value)
    assert resp.status_code == 400
    assert not await SystemConfiguration.exists(name='discord_invite_url')


async def test_invite_is_stored_canonical(db, app):
    resp = await _put(app, 'discord_invite_url', 'discord.com/invite/abc123')
    assert resp.status_code == 200, resp.text
    assert resp.json()['value'] == 'https://discord.gg/abc123'


async def test_unknown_key_is_refused(db, app):
    resp = await _put(app, 'custom_banner_html', '<script>1</script>')
    assert resp.status_code == 400
    assert not await SystemConfiguration.exists(name='custom_banner_html')


@pytest.mark.parametrize(('key', 'value'), [
    ('max_concurrent_players', 'lots'),
    ('max_concurrent_players', '0'),
    ('event_start_date', '10/23/2025'),
    ('join_page_match_preview', 'maybe'),
    ('station_format', 'hexagonal'),
    ('volunteer_comp_tiers', '8, -4'),
    ('tournament_hours_by_date', '{"2025-10-23": {"open": "22:00", "close": "09:00"}}'),
])
async def test_bad_values_are_400(db, app, key, value):
    assert (await _put(app, key, value)).status_code == 400


@pytest.mark.parametrize(('key', 'value', 'stored'), [
    ('max_concurrent_players', ' 40 ', '40'),
    ('join_page_match_preview', 'YES', 'true'),
    ('volunteer_comp_tiers', '16, 8,12', '8, 12, 16'),
    ('tournament_hours_by_date', '{"2025-10-23": {"open": "09:00", "close": "22:00"}}',
     '{"2025-10-23": {"open": "09:00", "close": "22:00"}}'),
])
async def test_good_values_are_normalized(db, app, key, value, stored):
    resp = await _put(app, key, value)
    assert resp.status_code == 200, resp.text
    assert resp.json()['value'] == stored


async def test_non_staff_gets_403_before_validation(db, app):
    _, raw = await create_user_token(username='plain', member=True)
    async with client_for(app, raw) as c:
        resp = await c.put('/api/config/not_a_key', json={'value': 'x'})
    assert resp.status_code == 403
