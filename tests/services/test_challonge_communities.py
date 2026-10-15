"""Which Challonge communities a reconnect asks for, and staff trimming the list."""

import pytest

from application.repositories.user_role_repository import UserRoleRepository
from application.services._challonge_communities import COMMUNITIES_CONFIG_KEY
from application.services.challonge_service import ChallongeService
from models import AuditLog, Role, Tenant, TenantMembership, Tournament, User


@pytest.fixture
async def staff(db):
    boss = await User.create(discord_id=7500, username='boss')
    await UserRoleRepository.add(boss, Role.STAFF)
    await TenantMembership.create(user=boss, tenant_id=1)
    return boss


@pytest.fixture
def challonge(monkeypatch):
    service = ChallongeService()

    class _OAuth:
        async def get_me(self, token):
            return {'username': 'sgl-bot'}

    monkeypatch.setattr(service, '_oauth_client', lambda: _OAuth())
    return service


async def _saved() -> list:
    tenant = await Tenant.get(id=1)
    return (tenant.config or {}).get(COMMUNITIES_CONFIG_KEY, [])


async def test_connecting_with_a_community_remembers_it(challonge, staff):
    await challonge.save_service_connection({'access_token': 'a'}, staff, community='SpeedGaming.challonge.com')
    await challonge.save_service_connection({'access_token': 'b'}, staff, community='alttprleague')
    await challonge.save_service_connection({'access_token': 'c'}, staff, community='speedgaming')
    await challonge.save_service_connection({'access_token': 'd'}, staff)
    assert await _saved() == ['speedgaming', 'alttprleague']


async def test_the_list_survives_a_disconnect(challonge, staff):
    await challonge.save_service_connection({'access_token': 'a'}, staff, community='speedgaming')
    await challonge.disconnect(staff)
    assert await challonge.communities_to_grant() == ['speedgaming']


async def test_tournament_communities_join_the_list_with_counts(challonge, staff):
    await challonge.save_service_connection({'access_token': 'a'}, staff, community='speedgaming')
    await Tournament.create(name='A', challonge_tournament_id='1', challonge_community='speedgaming')
    await Tournament.create(name='B', challonge_tournament_id='2', challonge_community='zsr')
    await Tournament.create(name='C', challonge_tournament_id='3', challonge_community='zsr')
    await Tournament.create(name='D', challonge_tournament_id='4')
    listed = await challonge.remembered_communities()
    assert [(c.slug, c.tournament_count, c.removable) for c in listed] == [
        ('speedgaming', 1, False), ('zsr', 2, False),
    ]


async def test_communities_to_grant_appends_a_typed_one(challonge, staff):
    await challonge.save_service_connection({'access_token': 'a'}, staff, community='speedgaming')
    assert await challonge.communities_to_grant(' https://zsr.challonge.com/x ') == ['speedgaming', 'zsr']
    assert await challonge.communities_to_grant('speedgaming') == ['speedgaming']
    with pytest.raises(ValueError, match='subdomain'):
        await challonge.communities_to_grant('not a community!')


async def test_staff_remove_an_unused_community(challonge, staff):
    await challonge.save_service_connection({'access_token': 'a'}, staff, community='speedgaming')
    await challonge.save_service_connection({'access_token': 'b'}, staff, community='old')
    await challonge.remove_community(staff, 'old')
    assert await _saved() == ['speedgaming']
    assert await AuditLog.filter(action='challonge.community_removed').count() == 1


async def test_a_community_with_linked_tournaments_cannot_be_removed(challonge, staff):
    await challonge.save_service_connection({'access_token': 'a'}, staff, community='speedgaming')
    await Tournament.create(name='A', challonge_tournament_id='1', challonge_community='speedgaming')
    with pytest.raises(ValueError, match='1 linked tournament uses speedgaming'):
        await challonge.remove_community(staff, 'speedgaming')
    assert await _saved() == ['speedgaming']


async def test_only_staff_remove_a_community(challonge, staff):
    await challonge.save_service_connection({'access_token': 'a'}, staff, community='old')
    player = await User.create(discord_id=7501, username='player')
    with pytest.raises(PermissionError):
        await challonge.remove_community(player, 'old')
