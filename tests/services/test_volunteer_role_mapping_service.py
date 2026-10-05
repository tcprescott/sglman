"""VolunteerRoleMappingService: positions confer roles on their assignees.

Real services on the in-memory ``db`` fixture, driving the schedule service the
way the admin UI does so the reconcile hooks fire from their actual call sites.
"""

import itertools

import pytest

from application.services.volunteer.volunteer_position_service import VolunteerPositionService
from application.services.volunteer.volunteer_role_mapping_service import (
    VolunteerRoleMappingService,
)
from application.services.volunteer.volunteer_schedule_service import VolunteerScheduleService
from models import (
    Role,
    RoleSource,
    User,
    UserRole,
    VolunteerAssignment,
    VolunteerPosition,
    VolunteerShift,
)
from tests.factories import utc

_ids = itertools.count(710000)


async def _user(name, *roles: Role) -> User:
    user = await User.create(discord_id=next(_ids), username=name, display_name=name)
    for role in roles:
        await UserRole.create(user=user, role=role)
    return user


async def _role_row(user: User, role: Role):
    return await UserRole.get_or_none(user=user, role=role, tenant_id=1)


@pytest.fixture
async def setup(db, stub_discord_queue):
    staff = await _user('staff', Role.STAFF)
    vol = await _user('vol', Role.VOLUNTEER)
    position = await VolunteerPosition.create(name='Proctor Desk')
    shift = await VolunteerShift.create(
        position=position, starts_at=utc(2026, 10, 4, 8), ends_at=utc(2026, 10, 4, 12),
    )
    return staff, vol, position, shift


class TestMappingManagement:
    async def test_only_staff_can_add(self, setup):
        _, _, position, _ = setup
        coordinator = await _user('coord', Role.VOLUNTEER_COORDINATOR)
        with pytest.raises(PermissionError):
            await VolunteerRoleMappingService().add_mapping(coordinator, position.id, Role.PROCTOR)

    @pytest.mark.parametrize('role', [
        Role.STAFF, Role.VOLUNTEER_COORDINATOR, Role.PRESET_MANAGER,
        Role.SYNC_ADMIN, Role.QUALIFIER_ADMIN, Role.SUPER_ADMIN,
    ])
    async def test_rejects_admin_roles(self, setup, role):
        staff, _, position, _ = setup
        with pytest.raises(ValueError):
            await VolunteerRoleMappingService().add_mapping(staff, position.id, role)

    async def test_rejects_duplicate(self, setup):
        staff, _, position, _ = setup
        service = VolunteerRoleMappingService()
        await service.add_mapping(staff, position.id, Role.PROCTOR)
        with pytest.raises(ValueError):
            await service.add_mapping(staff, position.id, Role.PROCTOR)

    async def test_add_grants_existing_assignees_and_remove_revokes(self, setup):
        staff, vol, position, shift = setup
        await VolunteerScheduleService().assign(staff, shift, vol, notify=False)
        assert await _role_row(vol, Role.PROCTOR) is None

        service = VolunteerRoleMappingService()
        mapping = await service.add_mapping(staff, position.id, Role.PROCTOR)
        row = await _role_row(vol, Role.PROCTOR)
        assert row is not None and row.source == RoleSource.VOLUNTEER

        await service.remove_mapping(staff, mapping.id)
        assert await _role_row(vol, Role.PROCTOR) is None


class TestAssignmentLifecycle:
    async def test_assign_grants_and_unassign_revokes(self, setup):
        staff, vol, position, shift = setup
        await VolunteerRoleMappingService().add_mapping(staff, position.id, Role.PROCTOR)
        schedule = VolunteerScheduleService()

        assignment, _ = await schedule.assign(staff, shift, vol, notify=False)
        row = await _role_row(vol, Role.PROCTOR)
        assert row is not None and row.source == RoleSource.VOLUNTEER

        await schedule.unassign(staff, assignment)
        assert await _role_row(vol, Role.PROCTOR) is None

    async def test_draft_confers_nothing_until_published(self, setup):
        staff, vol, position, shift = setup
        await VolunteerRoleMappingService().add_mapping(staff, position.id, Role.PROCTOR)
        schedule = VolunteerScheduleService()

        assignment, _ = await schedule.assign(staff, shift, vol, auto_generated=True)
        assert await _role_row(vol, Role.PROCTOR) is None

        await schedule.confirm_assignment(staff, assignment, notify=False)
        assert await _role_row(vol, Role.PROCTOR) is not None

    async def test_role_kept_while_another_shift_remains(self, setup):
        staff, vol, position, shift = setup
        later = await VolunteerShift.create(
            position=position, starts_at=utc(2026, 10, 5, 8), ends_at=utc(2026, 10, 5, 12),
        )
        await VolunteerRoleMappingService().add_mapping(staff, position.id, Role.PROCTOR)
        schedule = VolunteerScheduleService()
        first, _ = await schedule.assign(staff, shift, vol, notify=False)
        await schedule.assign(staff, later, vol, notify=False)

        await schedule.unassign(staff, first)
        assert await _role_row(vol, Role.PROCTOR) is not None

    async def test_finished_shift_still_confers(self, setup):
        staff, vol, position, _ = setup
        past = await VolunteerShift.create(
            position=position, starts_at=utc(2020, 1, 1, 8), ends_at=utc(2020, 1, 1, 12),
        )
        await VolunteerRoleMappingService().add_mapping(staff, position.id, Role.PROCTOR)
        await VolunteerScheduleService().assign(staff, past, vol, notify=False)
        assert await _role_row(vol, Role.PROCTOR) is not None

    async def test_release_revokes(self, setup):
        staff, vol, position, _ = setup
        future = await VolunteerShift.create(
            position=position, starts_at=utc(2099, 1, 1, 8), ends_at=utc(2099, 1, 1, 12),
        )
        await VolunteerRoleMappingService().add_mapping(staff, position.id, Role.PROCTOR)
        schedule = VolunteerScheduleService()
        assignment, _ = await schedule.assign(staff, future, vol, notify=False)

        await schedule.release(assignment.id, vol)
        assert await _role_row(vol, Role.PROCTOR) is None

    async def test_deleting_shift_revokes(self, setup):
        staff, vol, position, shift = setup
        await VolunteerRoleMappingService().add_mapping(staff, position.id, Role.PROCTOR)
        schedule = VolunteerScheduleService()
        await schedule.assign(staff, shift, vol, notify=False)

        await schedule.delete_shift(staff, shift)
        assert await _role_row(vol, Role.PROCTOR) is None

    async def test_deleting_position_revokes(self, setup):
        staff, vol, position, shift = setup
        await VolunteerRoleMappingService().add_mapping(staff, position.id, Role.PROCTOR)
        await VolunteerScheduleService().assign(staff, shift, vol, notify=False)

        await VolunteerPositionService().delete(staff, position)
        assert await _role_row(vol, Role.PROCTOR) is None
        assert not await VolunteerAssignment.filter(user=vol).exists()


class TestOtherSourcesPreserved:
    async def test_manual_role_survives_unassign(self, setup):
        staff, vol, position, shift = setup
        await UserRole.create(user=vol, role=Role.PROCTOR, source=RoleSource.MANUAL)
        await VolunteerRoleMappingService().add_mapping(staff, position.id, Role.PROCTOR)
        schedule = VolunteerScheduleService()
        assignment, _ = await schedule.assign(staff, shift, vol, notify=False)

        await schedule.unassign(staff, assignment)
        row = await _role_row(vol, Role.PROCTOR)
        assert row is not None and row.source == RoleSource.MANUAL

    async def test_volunteer_role_held_via_discord_is_left_to_discord(self, setup):
        staff, vol, position, shift = setup
        await UserRole.create(user=vol, role=Role.PROCTOR, source=RoleSource.DISCORD)
        await VolunteerRoleMappingService().add_mapping(staff, position.id, Role.PROCTOR)
        schedule = VolunteerScheduleService()
        assignment, _ = await schedule.assign(staff, shift, vol, notify=False)
        row = await _role_row(vol, Role.PROCTOR)
        assert row.source == RoleSource.DISCORD

        await schedule.unassign(staff, assignment)
        assert (await _role_row(vol, Role.PROCTOR)).source == RoleSource.DISCORD

    async def test_reconcile_never_raises(self, setup, monkeypatch):
        staff, vol, _, _ = setup
        service = VolunteerRoleMappingService()

        async def boom(*_a, **_kw):
            raise RuntimeError('db down')

        monkeypatch.setattr(service.mapping_repository, 'list_all', boom)
        assert await service.reconcile_users(staff, [vol.id]) == {}
