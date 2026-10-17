"""Linking, unlinking and syncing a Challonge bracket is staff's job.

The service used to admit the tournament's admin while the web app kept the
Challonge controls on the staff-only tab, so a tournament admin could do over
REST and MCP what the app never offered them. Thomas chose staff only.
"""

import pytest

from application.repositories.user_role_repository import UserRoleRepository
from application.services.challonge_service import ChallongeService
from models import Role, TenantMembership, Tournament, User


@pytest.fixture
async def linked(db):
    return await Tournament.create(name='Bracket Cup', challonge_tournament_id='T1')


@pytest.fixture
async def tournament_admin(linked, db):
    ta = await User.create(discord_id=6100, username='ta')
    await TenantMembership.create(user=ta, tenant_id=1)
    await linked.admins.add(ta)
    return ta


async def test_a_tournament_admin_cannot_link_unlink_or_sync(linked, tournament_admin):
    service = ChallongeService()
    with pytest.raises(PermissionError):
        await service.link_tournament(linked.id, 'T2', tournament_admin)
    with pytest.raises(PermissionError):
        await service.unlink_tournament(linked.id, tournament_admin)
    with pytest.raises(PermissionError):
        await service.sync_bracket(linked.id, tournament_admin, force=True)


async def test_staff_pass_the_gate(linked, db):
    boss = await User.create(discord_id=6101, username='boss')
    await UserRoleRepository.add(boss, Role.STAFF)
    await TenantMembership.create(user=boss, tenant_id=1)
    unlinked = await ChallongeService().unlink_tournament(linked.id, boss)
    assert unlinked.challonge_tournament_id is None
