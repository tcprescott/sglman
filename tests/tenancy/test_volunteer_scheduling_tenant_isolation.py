"""Cross-tenant isolation for volunteer scheduling.

``User`` is global, so anything keyed on a user (qualifications) or on a bare
id passed in by a coordinator (a position) is a place one community's data
can bleed into another's schedule.
"""

from datetime import timedelta

import pytest

from application.services.volunteer.volunteer_autoschedule_service import (
    VolunteerAutoscheduleService,
)
from application.services.volunteer.volunteer_schedule_service import VolunteerScheduleService
from application.tenant_context import tenant_scope
from models import (
    Role,
    UserRole,
    VolunteerAssignment,
    VolunteerAvailability,
    VolunteerAvailabilityStatus,
    VolunteerPosition,
    VolunteerQualification,
    VolunteerShift,
)
from tests.factories import join_community, make_user, utc


async def test_another_communitys_qualification_does_not_exclude_a_volunteer(two_tenants):
    a, b = two_tenants
    shared = await make_user(7001, 'shared')
    start = utc(2026, 10, 20, 8)
    with tenant_scope(b.id):
        b_only = await VolunteerPosition.create(name='B-only desk')
        await VolunteerQualification.create(user=shared, position=b_only)
    with tenant_scope(a.id):
        coordinator = await make_user(7002, 'coord')
        await join_community(coordinator, shared)
        await UserRole.create(user=coordinator, role=Role.VOLUNTEER_COORDINATOR)
        await UserRole.create(user=shared, role=Role.VOLUNTEER)
        desk = await VolunteerPosition.create(name='A desk')
        shift = await VolunteerShift.create(
            position=desk, starts_at=start, ends_at=start + timedelta(hours=4),
        )
        await VolunteerAvailability.create(
            user=shared, starts_at=start - timedelta(hours=1), ends_at=start + timedelta(hours=8),
            status=VolunteerAvailabilityStatus.AVAILABLE,
        )

        result = await VolunteerAutoscheduleService().generate_draft(
            coordinator, start - timedelta(hours=8), start + timedelta(hours=20),
        )

        assert result['created'] == 1
        assert await VolunteerAssignment.filter(shift=shift, user=shared).exists()


async def test_a_shift_cannot_hang_off_another_communitys_position(two_tenants):
    a, b = two_tenants
    start = utc(2026, 10, 20, 8)
    with tenant_scope(b.id):
        foreign = await VolunteerPosition.create(name='B secret desk')
    with tenant_scope(a.id):
        coordinator = await make_user(7003, 'coord-a')
        await join_community(coordinator)
        await UserRole.create(user=coordinator, role=Role.VOLUNTEER_COORDINATOR)
        own = await VolunteerPosition.create(name='A desk')
        svc = VolunteerScheduleService()

        with pytest.raises(ValueError, match="doesn't exist"):
            await svc.create_shift(coordinator, foreign.id, start, start + timedelta(hours=4))
        with pytest.raises(ValueError, match="doesn't exist"):
            await svc.generate_day_shifts(
                coordinator, '2026-10-20', [foreign.id], [('Shift 1', '08:00', '12:00')],
            )
        shift = await svc.create_shift(coordinator, own.id, start, start + timedelta(hours=4))
        with pytest.raises(ValueError, match="doesn't exist"):
            await svc.update_shift(coordinator, await svc.get_shift(shift.id), position_id=foreign.id)

        assert not await VolunteerShift.filter(position_id=foreign.id).exists()


async def test_a_qualification_cannot_name_another_communitys_position(two_tenants):
    from application.services.volunteer.volunteer_qualification_service import VolunteerQualificationService

    a, b = two_tenants
    with tenant_scope(b.id):
        b_only = await VolunteerPosition.create(name='B-only desk')
    with tenant_scope(a.id):
        coordinator = await make_user(7101, 'coord-q')
        volunteer = await make_user(7102, 'vol-q')
        await join_community(coordinator, volunteer)
        await UserRole.create(user=coordinator, role=Role.VOLUNTEER_COORDINATOR)

        with pytest.raises(ValueError, match="doesn't exist"):
            await VolunteerQualificationService().set_qualifications(coordinator, volunteer, [b_only.id])

    assert not await VolunteerQualification.filter(user=volunteer).exists()


async def test_the_full_schedule_shows_only_this_communitys_shifts(two_tenants):
    from datetime import date, time

    from application.utils.timezone import combine_local

    a, b = two_tenants
    day = combine_local(date(2026, 10, 23), time(0))
    with tenant_scope(b.id):
        b_desk = await VolunteerPosition.create(name='B desk')
        await VolunteerShift.create(
            position=b_desk, starts_at=day + timedelta(hours=8), ends_at=day + timedelta(hours=12),
        )
    with tenant_scope(a.id):
        viewer = await make_user(7101, 'viewer')
        await join_community(viewer)
        await UserRole.create(user=viewer, role=Role.VOLUNTEER)
        a_desk = await VolunteerPosition.create(name='A desk')
        await VolunteerShift.create(
            position=a_desk, starts_at=day + timedelta(hours=8), ends_at=day + timedelta(hours=12),
        )

        grid = await VolunteerScheduleService().day_grid(viewer, date(2026, 10, 23))

        assert [c.position for c in grid.columns] == ['A desk']
        assert await VolunteerScheduleService().grid_roles(viewer) == [(a_desk.id, 'A desk')]


async def test_the_full_schedule_refuses_someone_off_the_volunteer_hub(two_tenants):
    from datetime import date

    a, _ = two_tenants
    with tenant_scope(a.id):
        player = await make_user(7102, 'player')
        await join_community(player)
        with pytest.raises(PermissionError):
            await VolunteerScheduleService().day_grid(player, date(2026, 10, 23))
        with pytest.raises(PermissionError):
            await VolunteerScheduleService().grid_roles(player)
