"""The per-community Challonge grants: storing, picking, and asking for the right one."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.challonge_service import ChallongeService
from models import ChallongeConnection, User

pytestmark = pytest.mark.usefixtures("bypass_auth")


def make_service() -> ChallongeService:
    service = ChallongeService()
    oauth = MagicMock(get_me=AsyncMock(return_value={'username': 'syn'}))
    service._oauth_client = lambda: oauth
    return service


async def make_user(discord_id: int, username: str = 'u') -> User:
    return await User.create(discord_id=discord_id, username=username)


async def test_each_community_uses_its_own_grant(db):
    actor = await make_user(1, 'admin')
    service = make_service()
    await service.save_service_connection({'access_token': 'sg'}, actor, community='speedgaming')
    await service.save_service_connection({'access_token': 'own'}, actor, community=None)
    assert await service.get_valid_access_token(community='speedgaming') == 'sg'
    assert await service.get_valid_access_token(community=None) == 'own'
    assert await service.get_valid_access_token(community='elsewhere') == 'own'

async def test_regrant_replaces_only_its_own_community(db):
    actor = await make_user(1, 'admin')
    service = make_service()
    await service.save_service_connection({'access_token': 'sg1'}, actor, community='speedgaming')
    await service.save_service_connection({'access_token': 'own'}, actor, community=None)
    await service.save_service_connection({'access_token': 'sg2'}, actor, community='speedgaming')
    assert await ChallongeConnection.all().count() == 2
    assert await service.get_valid_access_token(community='speedgaming') == 'sg2'
    assert await service.get_valid_access_token(community=None) == 'own'

async def test_pre_split_row_serves_everything_until_a_grant_replaces_it(db):
    await ChallongeConnection.create(access_token='legacy', community=None)
    service = make_service()
    assert await service.get_valid_access_token(community=None) == 'legacy'
    assert await service.get_valid_access_token(community='speedgaming') == 'legacy'
    await service.save_service_connection(
        {'access_token': 'sg'}, await make_user(1, 'admin'), community='speedgaming',
    )
    assert not await ChallongeConnection.filter(access_token='legacy').exists()


async def test_token_is_asked_for_the_brackets_community():
    from application.utils.clients.challonge_client import ChallongeClient
    provider = AsyncMock(return_value='tok')
    client = ChallongeClient('id', 'secret', token_provider=provider)
    client._parse = AsyncMock(return_value={'data': {}})
    response = MagicMock(status=200)
    request = MagicMock()
    request.return_value.__aenter__ = AsyncMock(return_value=response)
    request.return_value.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock(request=request)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    with patch('aiohttp.ClientSession', return_value=session):
        await client.get_tournament_full('sglmmr26')
        await client.get_tournament_full('sgl26mmr', community='speedgaming')
    assert [c.kwargs for c in provider.await_args_list] == [
        {'community': None}, {'community': 'speedgaming'},
    ]
