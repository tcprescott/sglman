"""Integration tests for volunteer scheduling services (in-memory SQLite)."""

import itertools
from datetime import datetime, timedelta, timezone

import pytest

from application.services.volunteer_autoschedule_service import VolunteerAutoscheduleService
from application.services.volunteer_availability_service import VolunteerAvailabilityService
from application.services.volunteer_profile_service import VolunteerProfileService
from application.services.volunteer_schedule_service import VolunteerScheduleService
from models import (
    Role,
    User,
    UserRole,
    VolunteerAssignment,
    VolunteerAvailability,
    VolunteerAvailabilityStatus,
    VolunteerPosition,
    VolunteerQualification,
    VolunteerShift,
)


@pytest.fixture(autouse=True)
def stub_discord_queue(monkeypatch):
    """Capture enqueued DM coroutines without running them."""
    captured = []

    def capture(coro):
        captured.append(coro)

    monkeypatch.setattr('application.services.discord_queue.enqueue', capture)
    yield captured
    for coro in captured:
        coro.close()


UTC = timezone.utc

_next_discord_id = itertools.count(100000)


async def _user(name, *, roles=()):
    user = await User.create(discord_id=next(_next_discord_id), username=name, display_name=name)
    for role in roles:
        await UserRole.create(user=user, role=role)
    return user


async def _staff():
    return await _user('staff', roles=[Role.STAFF])


async def _opted_in_volunteer(name):
    user = await _user(name)
    await VolunteerProfileService().opt_in(user)
    return user


def _at(hour, day=4):
    return datetime(2026, 10, day, hour, 0, tzinfo=UTC)


# --- generate_day_shifts --------------------------------------------------

async def test_generate_day_shifts_counts_and_midnight(db):
    staff = await _staff()
    p1 = await VolunteerPosition.create(name='Check-in')
    p2 = await VolunteerPosition.create(name='Race Proctor')
    blocks = [('Shift 1', '08:00', '12:00'), ('Shift 4', '20:00', '00:00')]

    shifts = await VolunteerScheduleService().generate_day_shifts(
        staff, '2026-10-04', [p1.id, p2.id], blocks,
    )
    assert len(shifts) == 4  # 2 positions x 2 blocks
    # The 20:00–00:00 block must roll its end into the next day.
    overnight = [s for s in shifts if s.label == 'Shift 4']
    for s in overnight:
        assert s.ends_at > s.starts_at
        assert (s.ends_at - s.starts_at) == timedelta(hours=4)


# --- staggered generation -------------------------------------------------

def test_validate_stagger_rules():
    from application.services.volunteer_position_service import VolunteerPositionService
    validate = VolunteerPositionService._validate_stagger

    validate(None, None)   # both unset -> fixed blocks
    validate(240, 120)     # overlapping rolling shifts
    validate(240, 240)     # back-to-back, still continuous coverage

    with pytest.raises(ValueError, match='both'):
        validate(240, None)
    with pytest.raises(ValueError, match='both'):
        validate(None, 120)
    with pytest.raises(ValueError, match='positive'):
        validate(240, 0)
    with pytest.raises(ValueError, match='exceed'):
        validate(120, 240)


async def test_generate_day_shifts_staggered_position(db):
    staff = await _staff()
    tech = await VolunteerPosition.create(
        name='Broadcast Tech', shift_length_minutes=240, stagger_minutes=120,
    )
    # Coverage 08:00–20:00; 4h shifts starting every 2h.
    blocks = [
        ('Shift 1', '08:00', '12:00'),
        ('Shift 2', '12:00', '16:00'),
        ('Shift 3', '16:00', '20:00'),
    ]

    shifts = await VolunteerScheduleService().generate_day_shifts(
        staff, '2026-10-04', [tech.id], blocks,
    )
    shifts = sorted(shifts, key=lambda s: s.starts_at)
    # Starts at 08,10,12,14,16,18 -> 6 rolling shifts, each a single slot.
    assert len(shifts) == 6
    assert all(s.slots_needed == 1 and s.label is None for s in shifts)
    # Consecutive starts are offset by the 2h stagger (handoffs don't bunch up).
    for earlier, later in zip(shifts, shifts[1:]):
        assert later.starts_at - earlier.starts_at == timedelta(hours=2)
    # Full shifts run 4h; the final one is clamped to the 20:00 coverage end.
    assert all(s.ends_at - s.starts_at == timedelta(hours=4) for s in shifts[:-1])
    assert shifts[-1].ends_at - shifts[-1].starts_at == timedelta(hours=2)
    assert shifts[-1].ends_at == shifts[-2].ends_at  # both land on 20:00


async def test_generate_day_shifts_mixes_staggered_and_fixed(db):
    staff = await _staff()
    fixed = await VolunteerPosition.create(name='Check-in')
    tech = await VolunteerPosition.create(
        name='Broadcast Tech', shift_length_minutes=240, stagger_minutes=120,
    )
    blocks = [('Shift 1', '08:00', '12:00'), ('Shift 2', '12:00', '16:00')]

    shifts = await VolunteerScheduleService().generate_day_shifts(
        staff, '2026-10-04', [fixed.id, tech.id], blocks,
    )
    fixed_shifts = [s for s in shifts if s.position_id == fixed.id]
    tech_shifts = [s for s in shifts if s.position_id == tech.id]
    # The plain position keeps its two discrete labelled blocks.
    assert len(fixed_shifts) == 2
    assert {s.label for s in fixed_shifts} == {'Shift 1', 'Shift 2'}
    # The staggered position rolls across 08:00–16:00: starts 08,10,12,14.
    assert len(tech_shifts) == 4
    assert all(s.label is None for s in tech_shifts)


# --- assign ---------------------------------------------------------------

async def test_assign_then_duplicate_and_overlap_rejected(db):
    staff = await _staff()
    pos = await VolunteerPosition.create(name='Admin Desk')
    shift = await VolunteerShift.create(position=pos, starts_at=_at(8), ends_at=_at(12))
    other = await VolunteerShift.create(position=pos, starts_at=_at(10), ends_at=_at(14))
    vol = await _opted_in_volunteer('alice')
    svc = VolunteerScheduleService()

    assignment, warnings = await svc.assign(staff, shift, vol)
    assert assignment.id is not None
    assert warnings == []

    with pytest.raises(ValueError, match='already on this shift'):
        await svc.assign(staff, shift, vol)

    with pytest.raises(ValueError, match='overlapping'):
        await svc.assign(staff, other, vol)


async def test_assign_overfill_warns_but_allows(db):
    staff = await _staff()
    pos = await VolunteerPosition.create(name='Board Game Room')
    shift = await VolunteerShift.create(position=pos, starts_at=_at(8), ends_at=_at(12), slots_needed=1)
    a = await _opted_in_volunteer('a')
    b = await _opted_in_volunteer('b')
    svc = VolunteerScheduleService()

    await svc.assign(staff, shift, a)
    _, warnings = await svc.assign(staff, shift, b)
    assert any('slots filled' in w for w in warnings)
    assert await VolunteerAssignment.filter(shift=shift).count() == 2


async def test_assign_unavailable_warns(db):
    staff = await _staff()
    pos = await VolunteerPosition.create(name='Photography')
    shift = await VolunteerShift.create(position=pos, starts_at=_at(8), ends_at=_at(12))
    vol = await _opted_in_volunteer('grumpy')
    await VolunteerAvailability.create(
        user=vol, starts_at=_at(7), ends_at=_at(13),
        status=VolunteerAvailabilityStatus.UNAVAILABLE,
    )
    _, warnings = await VolunteerScheduleService().assign(staff, shift, vol)
    assert any('unavailable' in w.lower() for w in warnings)


# --- acknowledge ----------------------------------------------------------

async def test_acknowledge_sets_timestamp_and_guards_owner(db):
    staff = await _staff()
    pos = await VolunteerPosition.create(name='Admin Desk')
    shift = await VolunteerShift.create(position=pos, starts_at=_at(8), ends_at=_at(12))
    vol = await _opted_in_volunteer('owner')
    intruder = await _opted_in_volunteer('intruder')
    svc = VolunteerScheduleService()
    assignment, _ = await svc.assign(staff, shift, vol)

    acked = await svc.acknowledge(assignment.id, vol)
    assert acked.acknowledged_at is not None

    with pytest.raises(ValueError, match='your own'):
        await svc.acknowledge(assignment.id, intruder)


# --- coverage -------------------------------------------------------------

async def test_coverage_reports_understaffing(db):
    staff = await _staff()
    pos = await VolunteerPosition.create(name='Race Proctor')
    shift = await VolunteerShift.create(position=pos, starts_at=_at(8), ends_at=_at(12), slots_needed=2)
    vol = await _opted_in_volunteer('one')
    svc = VolunteerScheduleService()
    await svc.assign(staff, shift, vol)

    rows = await svc.coverage(_at(0), _at(23))
    assert len(rows) == 1
    assert rows[0]['filled'] == 1 and rows[0]['needed'] == 2
    assert rows[0]['understaffed'] is True


# --- auto-schedule --------------------------------------------------------

async def test_autoschedule_respects_qualification_and_availability(db):
    staff = await _staff()
    proctor = await VolunteerPosition.create(name='Race Proctor')
    tech = await VolunteerPosition.create(name='Broadcast Tech')
    shift = await VolunteerShift.create(position=proctor, starts_at=_at(8), ends_at=_at(12))

    qualified = await _opted_in_volunteer('qualified')
    await VolunteerQualification.create(user=qualified, position=proctor)
    await VolunteerAvailability.create(
        user=qualified, starts_at=_at(8), ends_at=_at(12),
        status=VolunteerAvailabilityStatus.AVAILABLE,
    )
    # Qualified only for a different position -> ineligible for this shift.
    wrong = await _opted_in_volunteer('wrongskill')
    await VolunteerQualification.create(user=wrong, position=tech)

    result = await VolunteerAutoscheduleService().generate_draft(staff, _at(0), _at(23))
    assert result['created'] == 1
    assignment = await VolunteerAssignment.get(shift=shift)
    assert assignment.user_id == qualified.id
    assert assignment.auto_generated is True


async def test_autoschedule_load_balances(db):
    staff = await _staff()
    pos = await VolunteerPosition.create(name='Check-in')
    s1 = await VolunteerShift.create(position=pos, starts_at=_at(8), ends_at=_at(12))
    s2 = await VolunteerShift.create(position=pos, starts_at=_at(12), ends_at=_at(16))
    a = await _opted_in_volunteer('aa')
    b = await _opted_in_volunteer('bb')

    result = await VolunteerAutoscheduleService().generate_draft(staff, _at(0), _at(23))
    assert result['created'] == 2
    # Each generalist volunteer should get one of the two non-overlapping shifts.
    holders = {a.user_id for a in await VolunteerAssignment.all()}
    assert holders == {a.id, b.id}


async def test_autoschedule_leaves_unfillable_open_and_clear_draft(db):
    staff = await _staff()
    pos = await VolunteerPosition.create(name='Admin Desk')
    shift = await VolunteerShift.create(position=pos, starts_at=_at(8), ends_at=_at(12), slots_needed=3)
    only = await _opted_in_volunteer('solo')

    auto = VolunteerAutoscheduleService()
    result = await auto.generate_draft(staff, _at(0), _at(23))
    assert result['created'] == 1
    assert result['unfilled'] and result['unfilled'][0]['open'] == 2

    # A manual assignment must survive clear_draft; drafts must not.
    manual = await _opted_in_volunteer('manual')
    await VolunteerScheduleService().assign(staff, shift, manual)
    removed = await auto.clear_draft(staff, _at(0), _at(23))
    assert removed == 1
    remaining = await VolunteerAssignment.filter(shift=shift)
    assert len(remaining) == 1 and remaining[0].user_id == manual.id


# --- reminders ------------------------------------------------------------

async def test_reminder_loop_fires_once(db, monkeypatch):
    from application.services import volunteer_reminder

    class _DummyDiscord:
        async def send_dm_with_volunteer_acknowledgment_button(self, *a, **k):
            return True, 'mock'

    monkeypatch.setattr(
        'application.services.discord_service.DiscordService', _DummyDiscord,
    )

    pos = await VolunteerPosition.create(name='Admin Desk')
    soon = datetime.now(UTC) + timedelta(minutes=30)
    shift = await VolunteerShift.create(
        position=pos, starts_at=soon, ends_at=soon + timedelta(hours=4),
    )
    vol = await _user('reminded')
    await VolunteerAssignment.create(shift=shift, user=vol)

    await volunteer_reminder._tick()
    assignment = await VolunteerAssignment.get(shift=shift)
    assert assignment.reminder_sent_at is not None
    first_stamp = assignment.reminder_sent_at

    # Second tick must not re-fire (already stamped -> filtered out).
    await volunteer_reminder._tick()
    assignment = await VolunteerAssignment.get(shift=shift)
    assert assignment.reminder_sent_at == first_stamp


async def test_reminder_skips_far_future_shift(db, monkeypatch):
    from application.services import volunteer_reminder

    class _DummyDiscord:
        async def send_dm_with_volunteer_acknowledgment_button(self, *a, **k):
            return True, 'mock'

    monkeypatch.setattr(
        'application.services.discord_service.DiscordService', _DummyDiscord,
    )

    pos = await VolunteerPosition.create(name='Admin Desk')
    far = datetime.now(UTC) + timedelta(hours=6)  # beyond default 60-min lead
    shift = await VolunteerShift.create(
        position=pos, starts_at=far, ends_at=far + timedelta(hours=4),
    )
    vol = await _user('later')
    await VolunteerAssignment.create(shift=shift, user=vol)

    await volunteer_reminder._tick()
    assignment = await VolunteerAssignment.get(shift=shift)
    assert assignment.reminder_sent_at is None


# --- reminder pool / profile ---------------------------------------------

async def test_assignable_pool_is_opted_in_users(db):
    await _staff()
    opted = await _opted_in_volunteer('opted')
    # Profile exists but never opted in -> excluded.
    not_opted = await _user('notopted')
    await VolunteerProfileService().get_or_create(not_opted)
    # No profile at all -> excluded.
    no_profile = await _user('noprofile')

    pool = await VolunteerProfileService().assignable_volunteers()
    ids = {u.id for u in pool}
    assert opted.id in ids
    assert not_opted.id not in ids
    assert no_profile.id not in ids
