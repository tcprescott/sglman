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


# ---------------------------------------------------------------------------
# The door: requests to join
# ---------------------------------------------------------------------------


@pytest.fixture
def captured_dms(monkeypatch):
    """Collect what would have been DM'd, without a Discord connection."""
    sent = []
    from application.services import discord as discord_pkg

    def _enqueue(coro):
        coro.close()  # never awaited; we only care that it was queued
        sent.append(True)

    monkeypatch.setattr(discord_pkg.discord_queue, 'enqueue', _enqueue)
    return sent


async def test_request_to_join_is_refused_for_an_existing_member(staff, db):
    outsider = await User.create(discord_id=4100, username='outsider')
    await TenantMembershipService().add_member(staff, outsider)
    with pytest.raises(ValueError) as exc:
        await TenantMembershipService().request_to_join(outsider, 1)
    assert 'already a member' in str(exc.value)


async def test_a_denied_request_can_be_reopened_not_duplicated(staff, db):
    from models import JoinRequestStatus, TenantJoinRequest

    outsider = await User.create(discord_id=4101, username='outsider')
    service = TenantMembershipService()
    request = await service.request_to_join(outsider, 1, 'let me in')
    await service.deny_request(staff, request.id)

    reopened = await service.request_to_join(outsider, 1, 'asking again')
    assert reopened.id == request.id
    assert reopened.status is JoinRequestStatus.PENDING
    assert reopened.message == 'asking again'
    # The decision fields are cleared, not left pointing at the old verdict.
    assert reopened.decided_by_id is None and reopened.decided_at is None
    assert await TenantJoinRequest.filter(user=outsider, tenant_id=1).count() == 1


async def test_approving_creates_the_membership(staff, db):
    outsider = await User.create(discord_id=4102, username='outsider')
    service = TenantMembershipService()
    request = await service.request_to_join(outsider, 1)
    await service.approve_request(staff, request.id)
    assert await service.is_member(outsider) is True


async def test_denying_creates_no_membership(staff, db):
    outsider = await User.create(discord_id=4103, username='outsider')
    service = TenantMembershipService()
    request = await service.request_to_join(outsider, 1)
    await service.deny_request(staff, request.id)
    assert await service.is_member(outsider) is False


async def test_a_decided_request_cannot_be_decided_twice(staff, db):
    outsider = await User.create(discord_id=4104, username='outsider')
    service = TenantMembershipService()
    request = await service.request_to_join(outsider, 1)
    await service.approve_request(staff, request.id)
    with pytest.raises(ValueError) as exc:
        await service.deny_request(staff, request.id)
    assert 'already been decided' in str(exc.value)


async def test_decisions_require_role_granting_authority(staff, db):
    outsider = await User.create(discord_id=4105, username='outsider')
    nobody = await User.create(discord_id=4106, username='nobody')
    service = TenantMembershipService()
    request = await service.request_to_join(outsider, 1)
    with pytest.raises(PermissionError):
        await service.approve_request(nobody, request.id)
    with pytest.raises(PermissionError):
        await service.deny_request(nobody, request.id)


async def test_another_communitys_request_is_not_found_not_forbidden(staff, db):
    """The message must not confirm that another community's request exists."""
    from application.errors import NotFoundError

    other = await Tenant.create(name='Other', slug='other')
    outsider = await User.create(discord_id=4107, username='outsider')
    service = TenantMembershipService()
    request = await service.request_to_join(outsider, other.id)

    with pytest.raises(NotFoundError):
        await service.approve_request(staff, request.id)


async def test_list_pending_is_scoped_and_excludes_decided(staff, db):
    other = await Tenant.create(name='Other', slug='other')
    here = await User.create(discord_id=4108, username='here')
    there = await User.create(discord_id=4109, username='there')
    decided = await User.create(discord_id=4110, username='decided')
    service = TenantMembershipService()

    await service.request_to_join(here, 1)
    await service.request_to_join(there, other.id)
    gone = await service.request_to_join(decided, 1)
    await service.deny_request(staff, gone.id)

    pending = await service.list_pending()
    assert [r.user.username for r in pending] == ['here']


async def test_the_join_audit_row_is_stamped_with_the_target_tenant(db):
    """The requester is not scoped to the tenant they are asking to join.

    Without the explicit scope the row would land in whatever community the
    requester happened to be looking at — or nowhere.
    """
    from models import AuditLog

    other = await Tenant.create(name='Other', slug='other')
    outsider = await User.create(discord_id=4111, username='outsider')
    await TenantMembershipService().request_to_join(outsider, other.id)

    row = await AuditLog.get(action='tenant.join_requested')
    assert row.tenant_id == other.id
    # And the requester is the actor: they acted on their own behalf.
    assert row.user_id == outsider.id


async def test_an_over_long_message_is_refused_not_truncated(db):
    outsider = await User.create(discord_id=4112, username='outsider')
    with pytest.raises(ValueError) as exc:
        await TenantMembershipService().request_to_join(outsider, 1, 'x' * 501)
    assert '500' in str(exc.value)


async def test_staff_are_notified_of_a_request(staff, captured_dms, db):
    outsider = await User.create(discord_id=4113, username='outsider')
    await TenantMembershipService().request_to_join(outsider, 1, 'hello')
    assert len(captured_dms) == 1  # the one STAFF member


async def test_the_requester_is_notified_on_approve_and_on_deny(staff, captured_dms, db):
    one = await User.create(discord_id=4114, username='one')
    two = await User.create(discord_id=4115, username='two')
    service = TenantMembershipService()
    r1 = await service.request_to_join(one, 1)
    r2 = await service.request_to_join(two, 1)
    captured_dms.clear()

    await service.approve_request(staff, r1.id)
    assert len(captured_dms) == 1
    await service.deny_request(staff, r2.id)
    assert len(captured_dms) == 2
