"""NavPreference: pins in one community never show up in another."""

from application.services import NavPreferenceService
from application.services.nav_preference_service import DEFAULT_PINS
from application.tenant_context import tenant_scope
from models import NavPreference, TenantMembership
from tests.factories import make_user


async def test_pins_do_not_leak_between_tenants(two_tenants):
    a, b = two_tenants
    member = await make_user(discord_id=850, username='nav_leak')
    for t in (a, b):
        await TenantMembership.create(user=member, tenant=t)
    service = NavPreferenceService()

    with tenant_scope(a.id):
        await service.save_pins(member, ['/live'])
        await service.save_open_sections(member, ['admin'])
    with tenant_scope(b.id):
        assert await service.load(member) == (list(DEFAULT_PINS), None)
        await service.save_pins(member, ['/checkin'])
    with tenant_scope(a.id):
        assert await service.load(member) == (['/live'], ['admin'])

    assert await NavPreference.filter(tenant_id=a.id).count() == 1
    assert await NavPreference.filter(tenant_id=b.id).count() == 1
