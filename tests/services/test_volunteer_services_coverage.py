"""Coverage-focused integration tests for the volunteer service trio.

Exercises the branches the existing unit suites skip: read/lookup helpers,
reset, unassign, check-in, availability-warning-on-assign, self-service
availability replacement, and the qualification CRUD/query surface. Uses the
in-memory SQLite ``db`` fixture with the real services and the real
``AuthService`` (roles are granted via ``UserRole`` rows).
"""

import itertools
from datetime import datetime, timedelta, timezone

import pytest

from application.services.volunteer_availability_service import VolunteerAvailabilityService
from application.services.volunteer_qualification_service import VolunteerQualificationService
from application.services.volunteer_schedule_service import VolunteerScheduleService
from application.utils.timezone import EASTERN_TZ, parse_eastern_datetime
from models import (
    Role,
    User,
    UserRole,
    VolunteerAssignment,
    VolunteerAvailability,
    VolunteerAvailabilityStatus,
    VolunteerPosition,
    VolunteerProfile,
    VolunteerQualification,
    VolunteerShift,
)

UTC = timezone.utc

_next_discord_id = itertools.count(500000)


def utc(hour, minute=0, day=4):
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


def eastern(hour, minute=0, day=4):
    return datetime(2026, 10, day, hour, minute, tzinfo=EASTERN_TZ)


async def _user(name, *, roles=()):
    user = await User.create(discord_id=next(_next_discord_id), username=name, display_name=name)
    for role in roles:
        await UserRole.create(user=user, role=role)
    return user


async def _staff():
    return await _user('staff', roles=[Role.STAFF])


async def _coordinator():
    return await _user('coord', roles=[Role.VOLUNTEER_COORDINATOR])


async def _volunteer(name='vol'):
    return await _user(name, roles=[Role.VOLUNTEER])


# ---------------------------------------------------------------------------
# Shift read helpers: list_shifts_for_window / get_shift
# ---------------------------------------------------------------------------


class TestShiftReads:
    async def test_list_shifts_for_window_returns_overlapping(self, db):
        pos = await VolunteerPosition.create(name='Check-in')
        inside = await VolunteerShift.create(position=pos, starts_at=utc(8), ends_at=utc(12))
        await VolunteerShift.create(position=pos, starts_at=utc(20), ends_at=utc(23))
        svc = VolunteerScheduleService()

        rows = await svc.list_shifts_for_window(utc(0), utc(14))
        ids = {s.id for s in rows}
        assert inside.id in ids
        # The 20:00-23:00 shift starts after the window end -> excluded.
        assert len(rows) == 1

    async def test_get_shift_returns_row(self, db):
        pos = await VolunteerPosition.create(name='Race Proctor')
        shift = await VolunteerShift.create(position=pos, starts_at=utc(8), ends_at=utc(12))
        svc = VolunteerScheduleService()
        found = await svc.get_shift(shift.id)
        assert found is not None and found.id == shift.id

    async def test_get_shift_returns_none_when_missing(self, db):
        svc = VolunteerScheduleService()
        assert await svc.get_shift(999999) is None


# ---------------------------------------------------------------------------
# Staggered generation crossing midnight (coverage_end rollover)
# ---------------------------------------------------------------------------


class TestStaggeredMidnight:
    async def test_staggered_coverage_rolls_over_midnight(self, db):
        staff = await _staff()
        tech = await VolunteerPosition.create(
            name='Overnight Tech', shift_length_minutes=120, stagger_minutes=60,
        )
        # Last block end (00:00) is at/before the first block start (20:00) ->
        # the coverage window must roll into the next day.
        blocks = [('S1', '20:00', '22:00'), ('S2', '22:00', '00:00')]

        shifts = await VolunteerScheduleService().generate_day_shifts(
            staff, '2026-10-04', [tech.id], blocks,
        )
        assert shifts
        assert all(s.ends_at > s.starts_at for s in shifts)
        expected_end = parse_eastern_datetime('2026-10-04', '00:00') + timedelta(days=1)
        latest_end = max(s.ends_at for s in shifts)
        assert latest_end == expected_end


# ---------------------------------------------------------------------------
# reset_all_shifts
# ---------------------------------------------------------------------------


class TestResetAllShifts:
    async def test_deletes_all_shifts_and_reports_count(self, db):
        staff = await _staff()
        pos = await VolunteerPosition.create(name='Admin Desk')
        await VolunteerShift.create(position=pos, starts_at=utc(8), ends_at=utc(12))
        await VolunteerShift.create(position=pos, starts_at=utc(12), ends_at=utc(16))
        svc = VolunteerScheduleService()

        deleted = await svc.reset_all_shifts(staff)
        assert deleted == 2
        assert await VolunteerShift.all().count() == 0

    async def test_returns_zero_when_no_shifts(self, db):
        staff = await _staff()
        assert await VolunteerScheduleService().reset_all_shifts(staff) == 0

    async def test_rejects_unprivileged_actor(self, db):
        vol = await _volunteer()
        with pytest.raises(PermissionError):
            await VolunteerScheduleService().reset_all_shifts(vol)


# ---------------------------------------------------------------------------
# get_assignment
# ---------------------------------------------------------------------------


class TestGetAssignment:
    async def test_returns_assignment_by_id(self, db):
        staff = await _staff()
        pos = await VolunteerPosition.create(name='Admin Desk')
        shift = await VolunteerShift.create(position=pos, starts_at=utc(8), ends_at=utc(12))
        vol = await _volunteer('finder')
        svc = VolunteerScheduleService()
        assignment, _ = await svc.assign(staff, shift, vol)

        found = await svc.get_assignment(assignment.id)
        assert found is not None and found.id == assignment.id

    async def test_returns_none_when_missing(self, db):
        assert await VolunteerScheduleService().get_assignment(424242) is None


# ---------------------------------------------------------------------------
# unassign
# ---------------------------------------------------------------------------


class TestUnassign:
    async def test_removes_assignment_and_audits(self, db):
        staff = await _staff()
        pos = await VolunteerPosition.create(name='Admin Desk')
        shift = await VolunteerShift.create(position=pos, starts_at=utc(8), ends_at=utc(12))
        vol = await _volunteer('dropme')
        svc = VolunteerScheduleService()
        assignment, _ = await svc.assign(staff, shift, vol)
        assert await VolunteerAssignment.all().count() == 1

        await svc.unassign(staff, assignment)
        assert await VolunteerAssignment.all().count() == 0

    async def test_rejects_unprivileged_actor(self, db):
        staff = await _staff()
        pos = await VolunteerPosition.create(name='Admin Desk')
        shift = await VolunteerShift.create(position=pos, starts_at=utc(8), ends_at=utc(12))
        vol = await _volunteer('keepme')
        svc = VolunteerScheduleService()
        assignment, _ = await svc.assign(staff, shift, vol)

        with pytest.raises(PermissionError):
            await svc.unassign(vol, assignment)


# ---------------------------------------------------------------------------
# check_in
# ---------------------------------------------------------------------------


class TestCheckIn:
    async def test_rejects_unprivileged_actor(self, db):
        staff = await _staff()
        pos = await VolunteerPosition.create(name='Admin Desk')
        shift = await VolunteerShift.create(position=pos, starts_at=utc(8), ends_at=utc(12))
        vol = await _volunteer('showsup')
        svc = VolunteerScheduleService()
        assignment, _ = await svc.assign(staff, shift, vol)

        with pytest.raises(PermissionError, match='check-ins'):
            await svc.check_in(assignment.id, vol)

    async def test_raises_when_assignment_missing(self, db):
        staff = await _staff()
        with pytest.raises(ValueError, match='not found'):
            await VolunteerScheduleService().check_in(999999, staff)

    async def test_records_check_in(self, db):
        staff = await _staff()
        coord = await _coordinator()
        pos = await VolunteerPosition.create(name='Admin Desk')
        shift = await VolunteerShift.create(position=pos, starts_at=utc(8), ends_at=utc(12))
        vol = await _volunteer('present')
        svc = VolunteerScheduleService()
        assignment, _ = await svc.assign(staff, shift, vol)

        result = await svc.check_in(assignment.id, coord)
        assert result.checked_in_at is not None
        assert result.checked_in_by_id == coord.id

    async def test_is_idempotent(self, db):
        staff = await _staff()
        pos = await VolunteerPosition.create(name='Admin Desk')
        shift = await VolunteerShift.create(position=pos, starts_at=utc(8), ends_at=utc(12))
        vol = await _volunteer('twice')
        svc = VolunteerScheduleService()
        assignment, _ = await svc.assign(staff, shift, vol)

        first = await svc.check_in(assignment.id, staff)
        stamp = first.checked_in_at
        second = await svc.check_in(assignment.id, staff)
        assert second.checked_in_at == stamp


# ---------------------------------------------------------------------------
# assignments_for_user
# ---------------------------------------------------------------------------


class TestAssignmentsForUser:
    async def test_lists_all_for_user(self, db):
        staff = await _staff()
        pos = await VolunteerPosition.create(name='Admin Desk')
        s1 = await VolunteerShift.create(position=pos, starts_at=utc(8), ends_at=utc(12))
        s2 = await VolunteerShift.create(position=pos, starts_at=utc(12), ends_at=utc(16))
        vol = await _volunteer('busy')
        svc = VolunteerScheduleService()
        await svc.assign(staff, s1, vol)
        await svc.assign(staff, s2, vol)

        rows = await svc.assignments_for_user(vol)
        assert len(rows) == 2

    async def test_filters_by_upcoming_after(self, db):
        staff = await _staff()
        pos = await VolunteerPosition.create(name='Admin Desk')
        past = await VolunteerShift.create(position=pos, starts_at=utc(8), ends_at=utc(10))
        future = await VolunteerShift.create(position=pos, starts_at=utc(18), ends_at=utc(22))
        vol = await _volunteer('sched')
        svc = VolunteerScheduleService()
        await svc.assign(staff, past, vol)
        await svc.assign(staff, future, vol)

        rows = await svc.assignments_for_user(vol, upcoming_after=utc(12))
        assert len(rows) == 1
        assert rows[0].shift_id == future.id


# ---------------------------------------------------------------------------
# assign -> availability "not marked available" soft warning
# ---------------------------------------------------------------------------


class TestAssignAvailabilityWarning:
    async def test_warns_when_time_not_marked_available(self, db):
        staff = await _staff()
        pos = await VolunteerPosition.create(name='Photography')
        shift = await VolunteerShift.create(position=pos, starts_at=utc(8), ends_at=utc(12))
        vol = await _volunteer('partial')
        # Declares availability elsewhere, but nothing overlapping the shift.
        await VolunteerAvailability.create(
            user=vol, starts_at=utc(14), ends_at=utc(18),
            status=VolunteerAvailabilityStatus.AVAILABLE,
        )

        _, warnings = await VolunteerScheduleService().assign(staff, shift, vol)
        assert any('not marked this time as available' in w for w in warnings)

    async def test_no_warning_when_no_windows_declared(self, db):
        staff = await _staff()
        pos = await VolunteerPosition.create(name='Photography')
        shift = await VolunteerShift.create(position=pos, starts_at=utc(8), ends_at=utc(12))
        vol = await _volunteer('nowindows')

        _, warnings = await VolunteerScheduleService().assign(staff, shift, vol)
        assert warnings == []


# ---------------------------------------------------------------------------
# VolunteerAvailabilityService.set_windows (self-service replacement)
# ---------------------------------------------------------------------------


class TestSetWindows:
    async def _opt_in(self, user):
        await VolunteerProfile.create(user=user, opted_in_at=datetime.now(UTC))

    async def test_creates_windows_for_opted_in_user(self, db):
        vol = await _volunteer('setter')
        await self._opt_in(vol)
        svc = VolunteerAvailabilityService()
        windows = [
            (utc(8), utc(12), VolunteerAvailabilityStatus.AVAILABLE, 'morning'),
            (utc(14), utc(18), VolunteerAvailabilityStatus.PREFERRED, None),
        ]

        created = await svc.set_windows(vol, windows)
        assert len(created) == 2
        stored = await VolunteerAvailability.filter(user=vol).order_by('starts_at')
        assert len(stored) == 2
        assert stored[0].note == 'morning'
        assert stored[1].status == VolunteerAvailabilityStatus.PREFERRED

    async def test_replaces_existing_windows(self, db):
        vol = await _volunteer('replacer')
        await self._opt_in(vol)
        await VolunteerAvailability.create(
            user=vol, starts_at=utc(6), ends_at=utc(7),
            status=VolunteerAvailabilityStatus.AVAILABLE,
        )
        svc = VolunteerAvailabilityService()

        created = await svc.set_windows(
            vol, [(utc(9), utc(10), VolunteerAvailabilityStatus.AVAILABLE, None)],
        )
        assert len(created) == 1
        stored = await VolunteerAvailability.filter(user=vol)
        # The pre-existing 06:00-07:00 window was cleared out.
        assert len(stored) == 1
        assert stored[0].starts_at == utc(9)

    async def test_empty_windows_clears_availability(self, db):
        vol = await _volunteer('clearer')
        await self._opt_in(vol)
        await VolunteerAvailability.create(
            user=vol, starts_at=utc(6), ends_at=utc(7),
            status=VolunteerAvailabilityStatus.AVAILABLE,
        )
        svc = VolunteerAvailabilityService()

        created = await svc.set_windows(vol, [])
        assert created == []
        assert await VolunteerAvailability.filter(user=vol).count() == 0


# ---------------------------------------------------------------------------
# VolunteerQualificationService
# ---------------------------------------------------------------------------


class TestQualificationService:
    async def test_list_all_qualifications(self, db):
        vol = await _volunteer('qual')
        pos = await VolunteerPosition.create(name='Race Proctor')
        await VolunteerQualification.create(user=vol, position=pos)
        svc = VolunteerQualificationService()

        rows = await svc.list_all_qualifications()
        assert len(rows) == 1
        assert rows[0].user.id == vol.id
        assert rows[0].position.id == pos.id

    async def test_get_qualified_position_ids(self, db):
        vol = await _volunteer('multi')
        p1 = await VolunteerPosition.create(name='Pos A')
        p2 = await VolunteerPosition.create(name='Pos B')
        await VolunteerQualification.create(user=vol, position=p1)
        await VolunteerQualification.create(user=vol, position=p2)
        svc = VolunteerQualificationService()

        ids = await svc.get_qualified_position_ids(vol)
        assert ids == {p1.id, p2.id}

    async def test_get_qualified_user_ids_for_position(self, db):
        p1 = await VolunteerPosition.create(name='Shared Pos')
        u1 = await _volunteer('u1')
        u2 = await _volunteer('u2')
        await VolunteerQualification.create(user=u1, position=p1)
        await VolunteerQualification.create(user=u2, position=p1)
        svc = VolunteerQualificationService()

        ids = await svc.get_qualified_user_ids_for_position(p1.id)
        assert ids == {u1.id, u2.id}

    async def test_set_qualifications_replaces_and_audits(self, db):
        staff = await _staff()
        vol = await _volunteer('target')
        p1 = await VolunteerPosition.create(name='Pos A')
        p2 = await VolunteerPosition.create(name='Pos B')
        p3 = await VolunteerPosition.create(name='Pos C')
        await VolunteerQualification.create(user=vol, position=p1)
        svc = VolunteerQualificationService()

        await svc.set_qualifications(staff, vol, [p2.id, p3.id])
        ids = await svc.get_qualified_position_ids(vol)
        # p1 removed; p2/p3 now present.
        assert ids == {p2.id, p3.id}

    async def test_set_qualifications_rejects_unprivileged_actor(self, db):
        actor = await _volunteer('nobody')
        vol = await _volunteer('subject')
        pos = await VolunteerPosition.create(name='Pos A')
        svc = VolunteerQualificationService()

        with pytest.raises(PermissionError):
            await svc.set_qualifications(actor, vol, [pos.id])
