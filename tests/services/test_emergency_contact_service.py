"""EmergencyContactService — saving your own, the staff gate, and the log every look leaves."""

import json

import pytest

from application.errors import FeatureDisabledError
from application.services.audit_service import AuditActions
from application.services.emergency_contact_service import (
    NAME_MAX_LENGTH,
    EmergencyContactService,
)
from application.services.tenant_membership_service import TenantMembershipService
from models import (
    AuditLog,
    EmergencyContact,
    FeatureFlag,
    Role,
    TenantFeatureFlag,
    TenantMembership,
    UserRole,
)
from tests.conftest import DEFAULT_TEST_TENANT_ID
from tests.factories import make_user

pytestmark = pytest.mark.usefixtures("db")


@pytest.fixture
async def member():
    user = await make_user(discord_id=600, username='member')
    await TenantMembership.create(user=user, tenant_id=DEFAULT_TEST_TENANT_ID)
    return user


@pytest.fixture
async def staff():
    user = await make_user(discord_id=601, username='staffer')
    await UserRole.create(user=user, role=Role.STAFF, tenant_id=DEFAULT_TEST_TENANT_ID)
    return user


async def _actions() -> list[str]:
    return [a.action for a in await AuditLog.all().order_by('id')]


async def test_saving_creates_a_contact_with_tidied_fields(member):
    contact = await EmergencyContactService().save_mine(
        member, '  Jordan   Rivera ', '  ', ' +1 (555) 014-2 ',
    )

    assert (contact.name, contact.relationship, contact.phone) == (
        'Jordan Rivera', None, '+1 (555) 014-2',
    )
    assert await _actions() == [AuditActions.EMERGENCY_CONTACT_SAVED]


async def test_resaving_the_same_values_writes_nothing(member):
    service = EmergencyContactService()
    await service.save_mine(member, 'Jordan', 'Sibling', '555 0142')
    await service.save_mine(member, 'Jordan', 'Sibling', '555 0142')
    assert await _actions() == [AuditActions.EMERGENCY_CONTACT_SAVED]


async def test_editing_updates_the_one_row(member):
    service = EmergencyContactService()
    await service.save_mine(member, 'Jordan', 'Sibling', '555 0142')
    await service.save_mine(member, 'Sam', 'Parent', '555 0199')

    rows = await EmergencyContact.all()
    assert [(r.name, r.phone) for r in rows] == [('Sam', '555 0199')]


@pytest.mark.parametrize('name, phone', [
    ('', '555 0142'),
    ('Jordan', ''),
    ('Jordan', 'call my sister'),
    ('Jordan', '12'),
    ('x' * (NAME_MAX_LENGTH + 1), '555 0142'),
])
async def test_bad_input_is_refused(member, name, phone):
    with pytest.raises(ValueError):
        await EmergencyContactService().save_mine(member, name, None, phone)
    assert not await EmergencyContact.exists()


async def test_a_non_member_cannot_add_one():
    outsider = await make_user(discord_id=602, username='outsider')
    with pytest.raises(ValueError):
        await EmergencyContactService().save_mine(outsider, 'Jordan', None, '555 0142')


async def test_removing_deletes_the_row(member):
    service = EmergencyContactService()
    await service.save_mine(member, 'Jordan', None, '555 0142')
    await service.remove_mine(member)

    assert not await EmergencyContact.exists()
    assert await service.get_mine(member) is None
    assert await _actions() == [
        AuditActions.EMERGENCY_CONTACT_SAVED, AuditActions.EMERGENCY_CONTACT_REMOVED,
    ]


async def test_staff_opening_a_contact_logs_it_and_stamps_the_contact(member, staff):
    service = EmergencyContactService()
    await service.save_mine(member, 'Jordan', None, '555 0142')

    contact = await service.open_for(staff, member)

    assert contact.phone == '555 0142'
    log = await AuditLog.filter(action=AuditActions.EMERGENCY_CONTACT_VIEWED).get()
    assert log.user_id == staff.id
    assert json.loads(log.details)['user_id'] == member.id
    mine = await service.get_mine(member)
    assert mine.last_viewed_by.id == staff.id
    assert mine.last_viewed_at is not None


async def test_a_look_at_a_member_with_no_contact_is_still_logged(member, staff):
    assert await EmergencyContactService().open_for(staff, member) is None
    log = await AuditLog.filter(action=AuditActions.EMERGENCY_CONTACT_VIEWED).get()
    details = json.loads(log.details)
    assert (details['user_id'], details['contact_id']) == (member.id, None)


async def test_only_staff_can_open_a_contact(member):
    proctor = await make_user(discord_id=603, username='proctor')
    await UserRole.create(user=proctor, role=Role.PROCTOR, tenant_id=DEFAULT_TEST_TENANT_ID)
    await EmergencyContactService().save_mine(member, 'Jordan', None, '555 0142')

    for outsider in (member, proctor):
        with pytest.raises(PermissionError):
            await EmergencyContactService().open_for(outsider, member)
    assert not await AuditLog.filter(action=AuditActions.EMERGENCY_CONTACT_VIEWED).exists()


async def test_audit_rows_never_carry_the_contact(member, staff):
    service = EmergencyContactService()
    await service.save_mine(member, 'SECRETNAME', 'SECRETREL', '555 0142')
    await service.open_for(staff, member)
    await service.remove_mine(member)

    for log in await AuditLog.all():
        details = str(log.details)
        assert 'SECRET' not in details and '0142' not in details


async def test_removing_a_member_deletes_their_contact(member, staff):
    await EmergencyContactService().save_mine(member, 'Jordan', None, '555 0142')
    await TenantMembershipService().remove_member(staff, member)
    assert not await EmergencyContact.exists()


async def test_the_flag_being_off_hides_everything(member, staff):
    await TenantFeatureFlag.filter(
        tenant_id=DEFAULT_TEST_TENANT_ID, flag=FeatureFlag.EMERGENCY_CONTACTS.value,
    ).update(enabled=False)
    service = EmergencyContactService()

    with pytest.raises(FeatureDisabledError):
        await service.get_mine(member)
    with pytest.raises(FeatureDisabledError):
        await service.save_mine(member, 'Jordan', None, '555 0142')
    with pytest.raises(FeatureDisabledError):
        await service.remove_mine(member)
    with pytest.raises(FeatureDisabledError):
        await service.open_for(staff, member)
