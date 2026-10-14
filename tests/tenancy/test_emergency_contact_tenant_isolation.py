"""Emergency contacts never cross communities.

A contact given to one community is for that community's staff only, even when
the same person is a member, or a staff member, of both.
"""

from application.services.emergency_contact_service import EmergencyContactService
from application.tenant_context import tenant_scope
from models import AuditLog, EmergencyContact, Role, TenantMembership, UserRole
from tests.factories import make_user


async def test_contacts_do_not_leak_across_tenants(two_tenants):
    a, b = two_tenants
    member = await make_user(discord_id=730, username='both-member')
    staff = await make_user(discord_id=731, username='both-staff')
    for tenant in (a, b):
        await TenantMembership.create(user=member, tenant=tenant)
        await UserRole.create(user=staff, role=Role.STAFF, tenant=tenant)

    service = EmergencyContactService()
    with tenant_scope(a.id):
        await service.save_mine(member, 'Given to A', None, '555 0001')

    with tenant_scope(b.id):
        assert await service.get_mine(member) is None
        assert await service.open_for(staff, member) is None
        await service.remove_mine(member)
        await service.save_mine(member, 'Given to B', None, '555 0002')

    with tenant_scope(a.id):
        assert (await service.open_for(staff, member)).name == 'Given to A'
    assert await EmergencyContact.filter(user=member).count() == 2


async def test_staff_of_another_community_cannot_open_a_contact(two_tenants):
    a, b = two_tenants
    member = await make_user(discord_id=740, username='a-member')
    b_staff = await make_user(discord_id=741, username='b-staff')
    await TenantMembership.create(user=member, tenant=a)
    await UserRole.create(user=b_staff, role=Role.STAFF, tenant=b)

    service = EmergencyContactService()
    with tenant_scope(a.id):
        await service.save_mine(member, 'Jordan', None, '555 0142')
        try:
            await service.open_for(b_staff, member)
        except PermissionError:
            pass
        else:
            raise AssertionError("another community's staff opened the contact")
    with tenant_scope(b.id):
        assert await service.open_for(b_staff, member) is None
    contact = await EmergencyContact.get(user=member)
    assert contact.last_viewed_by_id is None
    assert await AuditLog.filter(user=b_staff, tenant_id=a.id).count() == 0
