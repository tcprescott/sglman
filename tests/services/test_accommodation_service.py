"""AccommodationService — the request lifecycle, the staff gate, and what the audit keeps out."""

import pytest

from application.errors import FeatureDisabledError
from application.services.accommodation_service import (
    DETAILS_MAX_LENGTH,
    AccommodationService,
)
from application.services.audit_service import AuditActions
from application.services.feature_flag_service import reset_flag_cache
from models import (
    AccommodationRequest,
    AccommodationStatus,
    AuditLog,
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
    user = await make_user(discord_id=500, username='asker')
    await TenantMembership.create(user=user, tenant_id=DEFAULT_TEST_TENANT_ID)
    return user


@pytest.fixture
async def staff():
    user = await make_user(discord_id=501, username='staffer')
    await UserRole.create(user=user, role=Role.STAFF, tenant_id=DEFAULT_TEST_TENANT_ID)
    return user


async def _actions() -> list[str]:
    return [a.action for a in await AuditLog.all().order_by('id')]


async def test_requesting_creates_a_new_request(member):
    request = await AccommodationService().set_my_request(member, True, '  ramp to stage  ')

    assert request.status is AccommodationStatus.NEW
    assert request.details == 'ramp to stage'
    assert await _actions() == [AuditActions.ACCOMMODATION_REQUESTED]


async def test_details_are_optional(member):
    request = await AccommodationService().set_my_request(member, True, '   ')
    assert request.details is None


async def test_details_over_the_limit_are_refused(member):
    with pytest.raises(ValueError):
        await AccommodationService().set_my_request(member, True, 'x' * (DETAILS_MAX_LENGTH + 1))
    assert not await AccommodationRequest.exists()


async def test_a_non_member_cannot_request():
    outsider = await make_user(discord_id=502, username='outsider')
    with pytest.raises(ValueError):
        await AccommodationService().set_my_request(outsider, True, 'hi')


async def test_unchecking_withdraws_and_clears_details_but_keeps_staff_notes(member, staff):
    service = AccommodationService()
    request = await service.set_my_request(member, True, 'quiet room')
    await service.update_request(staff, request.id, AccommodationStatus.ACKNOWLEDGED, 'booked room 2')

    await service.set_my_request(member, False)

    await request.refresh_from_db()
    assert request.status is AccommodationStatus.WITHDRAWN
    assert request.details is None
    assert request.staff_notes == 'booked room 2'


async def test_asking_again_after_withdrawing_reopens_as_new(member):
    service = AccommodationService()
    first = await service.set_my_request(member, True, 'a')
    await service.set_my_request(member, False)

    again = await service.set_my_request(member, True, 'b')

    assert again.id == first.id
    assert again.status is AccommodationStatus.NEW
    assert again.details == 'b'


async def test_editing_details_on_a_handled_request_sends_it_back_to_new(member, staff):
    service = AccommodationService()
    request = await service.set_my_request(member, True, 'a')
    await service.update_request(staff, request.id, AccommodationStatus.ARRANGED, None)

    await service.set_my_request(member, True, 'a, and also b')

    await request.refresh_from_db()
    assert request.status is AccommodationStatus.NEW


async def test_resaving_identical_details_is_a_no_op(member, staff):
    service = AccommodationService()
    request = await service.set_my_request(member, True, 'a')
    await service.update_request(staff, request.id, AccommodationStatus.ARRANGED, None)
    before = await _actions()

    await service.set_my_request(member, True, 'a')

    await request.refresh_from_db()
    assert request.status is AccommodationStatus.ARRANGED
    assert await _actions() == before


async def test_only_staff_can_read_or_update(member):
    service = AccommodationService()
    request = await service.set_my_request(member, True, 'a')

    with pytest.raises(PermissionError):
        await service.list_requests(member)
    with pytest.raises(PermissionError):
        await service.requesting_user_ids(member)
    with pytest.raises(PermissionError):
        await service.update_request(member, request.id, AccommodationStatus.ARRANGED, 'x')


async def test_staff_list_hides_withdrawn_unless_asked(member, staff):
    service = AccommodationService()
    other = await make_user(discord_id=503, username='other')
    await TenantMembership.create(user=other, tenant_id=DEFAULT_TEST_TENANT_ID)
    await service.set_my_request(member, True, 'a')
    await service.set_my_request(other, True, 'b')
    await service.set_my_request(other, False)

    assert [r.user_id for r in await service.list_requests(staff)] == [member.id]
    assert len(await service.list_requests(staff, include_withdrawn=True)) == 2
    assert await service.requesting_user_ids(staff) == {member.id}


async def test_staff_cannot_withdraw_or_reopen_on_a_members_behalf(member, staff):
    service = AccommodationService()
    request = await service.set_my_request(member, True, 'a')

    with pytest.raises(ValueError):
        await service.update_request(staff, request.id, AccommodationStatus.WITHDRAWN, None)

    await service.set_my_request(member, False)
    with pytest.raises(ValueError):
        await service.update_request(staff, request.id, AccommodationStatus.NEW, None)
    # Notes on a withdrawn request are still editable.
    await service.update_request(staff, request.id, AccommodationStatus.WITHDRAWN, 'closed out')
    await request.refresh_from_db()
    assert request.staff_notes == 'closed out'


async def test_status_and_notes_are_audited_separately(member, staff):
    service = AccommodationService()
    request = await service.set_my_request(member, True, 'a')

    await service.update_request(staff, request.id, AccommodationStatus.ACKNOWLEDGED, 'noted')

    assert await _actions() == [
        AuditActions.ACCOMMODATION_REQUESTED,
        AuditActions.ACCOMMODATION_STATUS_CHANGED,
        AuditActions.ACCOMMODATION_NOTES_UPDATED,
    ]


async def test_audit_rows_never_carry_the_free_text(member, staff):
    service = AccommodationService()
    request = await service.set_my_request(member, True, 'SECRET-DETAIL')
    await service.set_my_request(member, True, 'SECRET-DETAIL-2')
    await service.update_request(staff, request.id, AccommodationStatus.ARRANGED, 'SECRET-NOTE')
    await service.set_my_request(member, False)

    for log in await AuditLog.all():
        assert 'SECRET' not in str(log.details)


async def test_the_flag_being_off_hides_everything(member, staff):
    await TenantFeatureFlag.filter(
        tenant_id=DEFAULT_TEST_TENANT_ID, flag=FeatureFlag.ADA_ACCOMMODATIONS.value,
    ).update(enabled=False)
    service = AccommodationService()

    with pytest.raises(FeatureDisabledError):
        await service.get_mine(member)
    with pytest.raises(FeatureDisabledError):
        await service.set_my_request(member, True, 'a')
    with pytest.raises(FeatureDisabledError):
        await service.list_requests(staff)


async def _arranged(member, staff, note):
    service = AccommodationService()
    request = await service.set_my_request(member, True, 'member-only details')
    await service.update_request(staff, request.id, AccommodationStatus.ARRANGED, note)
    return request


async def test_schedule_notes_go_to_staff_and_proctors_only(member, staff):
    await _arranged(member, staff, 'chair at station 3')
    proctor = await make_user(discord_id=510, username='proctor')
    await UserRole.create(user=proctor, role=Role.PROCTOR, tenant_id=DEFAULT_TEST_TENANT_ID)
    stream_manager = await make_user(discord_id=511, username='sm')
    await UserRole.create(user=stream_manager, role=Role.STREAM_MANAGER, tenant_id=DEFAULT_TEST_TENANT_ID)
    service = AccommodationService()

    assert await service.arranged_notes_for(staff, [member.id]) == {member.id: 'chair at station 3'}
    assert await service.arranged_notes_for(proctor, [member.id]) == {member.id: 'chair at station 3'}
    assert await service.arranged_notes_for(stream_manager, [member.id]) == {}
    assert await service.arranged_notes_for(member, [member.id]) == {}
    assert await service.arranged_notes_for(None, [member.id]) == {}


async def test_schedule_notes_never_include_the_members_own_details(member, staff):
    await _arranged(member, staff, None)
    notes = await AccommodationService().arranged_notes_for(staff, [member.id])
    assert notes == {member.id: ''}
    assert 'member-only' not in str(notes)


async def test_schedule_notes_skip_requests_that_are_not_arranged(member, staff):
    service = AccommodationService()
    request = await service.set_my_request(member, True, 'x')
    await service.update_request(staff, request.id, AccommodationStatus.ACKNOWLEDGED, 'pending venue')
    assert await service.arranged_notes_for(staff, [member.id]) == {}


async def test_schedule_notes_are_empty_when_the_flag_is_off(member, staff):
    await _arranged(member, staff, 'n')
    await TenantFeatureFlag.filter(
        tenant_id=DEFAULT_TEST_TENANT_ID, flag=FeatureFlag.ADA_ACCOMMODATIONS.value,
    ).update(enabled=False)
    reset_flag_cache()  # a new request would read the flag fresh
    assert await AccommodationService().arranged_notes_for(staff, [member.id]) == {}
