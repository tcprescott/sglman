"""One tenant's rows must never complete another tenant's setup checklist.

``TenantSetupService`` touches five scoped models in one derivation. If any of
them lost its scoping, a busy community would mark a brand-new one "Ready" and
``/platform`` would report a community as set up that has nothing in it.
"""

from application.repositories.user_role_repository import UserRoleRepository
from application.services.system_config_service import (
    KEY_EVENT_END_DATE,
    KEY_EVENT_START_DATE,
    SystemConfigService,
)
from application.services.tenant_setup_service import TenantSetupService
from application.tenant_context import tenant_scope
from models import Role, Stage, Tournament, TournamentPlayers, User


async def test_a_full_tenant_does_not_complete_an_empty_tenants_checklist(two_tenants):
    tenant_a, tenant_b = two_tenants
    user = await User.create(discord_id=7700, username='busy')

    with tenant_scope(tenant_a.id):
        await UserRoleRepository.add(user, Role.STAFF)
        tournament = await Tournament.create(name='A')
        await TournamentPlayers.create(tournament=tournament, user=user)
        await Stage.create(name='Stage 1')
        await SystemConfigService.set_raw(KEY_EVENT_START_DATE, '2026-01-01', user)
        await SystemConfigService.set_raw(KEY_EVENT_END_DATE, '2026-01-03', user)
        assert TenantSetupService.is_ready(await TenantSetupService().status()) is True

    with tenant_scope(tenant_b.id):
        steps = await TenantSetupService().status()
    assert not any(s.done for s in steps)
    assert TenantSetupService.is_ready(steps) is False


async def test_status_for_does_not_leak_between_the_two(two_tenants):
    tenant_a, tenant_b = two_tenants
    user = await User.create(discord_id=7701, username='busy2')
    with tenant_scope(tenant_a.id):
        await UserRoleRepository.add(user, Role.STAFF)

    a_steps = {s.key: s for s in await TenantSetupService.status_for(tenant_a.id)}
    b_steps = {s.key: s for s in await TenantSetupService.status_for(tenant_b.id)}
    assert a_steps['staff'].done is True
    assert b_steps['staff'].done is False
