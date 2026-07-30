"""Membership as a managed thing rather than a write-only table."""

import pytest

from application.repositories.user_role_repository import UserRoleRepository
from application.services.tenant_membership_service import TenantMembershipService
from application.tenant_context import tenant_scope
from models import Role, Tenant, TenantMembership, User


@pytest.fixture
async def staff(db):
    boss = await User.create(discord_id=4000, username='boss')
    # The repository is below the invariant — only the service layer pairs a role
    # with a membership — so the fixture writes both by hand.
    await UserRoleRepository.add(boss, Role.STAFF)
    await TenantMembership.create(user=boss, tenant_id=1)
    return boss


async def test_add_member_requires_role_granting_authority(db):
    nobody = await User.create(discord_id=4001, username='nobody')
    target = await User.create(discord_id=4002, username='target')
    with pytest.raises(PermissionError):
        await TenantMembershipService().add_member(nobody, target)


async def test_add_member_is_idempotent(staff, db):
    target = await User.create(discord_id=4003, username='target')
    service = TenantMembershipService()
    await service.add_member(staff, target)
    await service.add_member(staff, target)
    assert await TenantMembership.filter(user=target, tenant_id=1).count() == 1


async def test_remove_member_refuses_while_roles_are_held(staff, db):
    # staff itself holds STAFF here, so it is the natural subject.
    with pytest.raises(ValueError) as exc:
        await TenantMembershipService().remove_member(staff, staff)
    assert 'revoke' in str(exc.value).lower()
    assert await TenantMembershipService().is_member(staff) is True


async def test_remove_member_succeeds_once_roles_are_revoked(staff, db):
    target = await User.create(discord_id=4004, username='target')
    service = TenantMembershipService()
    await UserRoleRepository.add(target, Role.PROCTOR)
    await service.add_member(staff, target)

    with pytest.raises(ValueError):
        await service.remove_member(staff, target)

    await UserRoleRepository.remove(target, Role.PROCTOR)
    await service.remove_member(staff, target)
    assert await service.is_member(target) is False


async def test_remove_member_reports_a_non_member(staff, db):
    stranger = await User.create(discord_id=4005, username='stranger')
    with pytest.raises(ValueError) as exc:
        await TenantMembershipService().remove_member(staff, stranger)
    assert 'not a member' in str(exc.value).lower()


async def test_list_members_returns_only_this_tenants_members(staff, db):
    other = await Tenant.create(name='Other', slug='other')
    here = await User.create(discord_id=4006, username='here')
    elsewhere = await User.create(discord_id=4007, username='elsewhere')
    await TenantMembershipService().add_member(staff, here)
    await TenantMembership.create(user=elsewhere, tenant=other)

    names = {u.username for u in await TenantMembershipService().list_members()}
    assert 'here' in names
    assert 'elsewhere' not in names

    with tenant_scope(other.id):
        names_there = {u.username for u in await TenantMembershipService().list_members()}
    assert names_there == {'elsewhere'}


async def test_membership_changes_are_audited_and_published(staff, db, monkeypatch):
    from application.events import EventType, event_bus

    published = []
    monkeypatch.setattr(event_bus, 'publish', lambda e: published.append(e))

    target = await User.create(discord_id=4008, username='target')
    service = TenantMembershipService()
    await service.add_member(staff, target)
    await service.remove_member(staff, target)

    from models import AuditLog
    actions = [row.action for row in await AuditLog.all()]
    assert 'tenant.member_added' in actions
    assert 'tenant.member_removed' in actions
    assert [e.event_type for e in published] == [
        EventType.TENANT_MEMBER_ADDED, EventType.TENANT_MEMBER_REMOVED,
    ]


async def test_ensure_member_is_idempotent_and_writes_no_audit(db):
    from models import AuditLog

    target = await User.create(discord_id=4009, username='target')
    await TenantMembershipService.ensure_member(target)
    await TenantMembershipService.ensure_member(target)
    assert await TenantMembership.filter(user=target, tenant_id=1).count() == 1
    # The role grant that calls this is audited in its own right.
    assert await AuditLog.filter(action='tenant.member_added').count() == 0


async def test_addable_users_offers_non_members_only(staff, db):
    already = await User.create(discord_id=4010, username='already')
    await TenantMembershipService().add_member(staff, already)
    await User.create(discord_id=4011, username='outsider')

    names = {u.username for u in await TenantMembershipService().addable_users()}
    assert 'outsider' in names
    assert 'already' not in names
    assert 'boss' not in names


async def test_addable_users_never_offers_the_system_actor(staff, db):
    from application.repositories.user_repository import UserRepository

    await UserRepository.get_or_create_system_user()
    names = {u.username for u in await TenantMembershipService().addable_users()}
    assert 'System' not in names
