"""Dev-seed fixtures for one tenant's volunteer scheduling surface.

Split out of ``seed_dev.py`` when that module crossed the 800-line budget,
following the ``seed_observability_for_tenant`` / ``seed_brackets_for_tenant``
convention already used there: one module per domain, called from inside the
caller's ``tenant_scope``. Idempotent (``get_or_create`` / existence-guarded)
and tenant-stamped like every other seeded row.

The seeded pool is deliberately assignable: the VOLUNTEER role grants in
``seed_dev.py`` mirror the opted-in + qualified + available users created here,
so the Vol. Roster tab and the auto-scheduler have something real to show
(``VolunteerProfileService.assignable_volunteers`` filters on ``Role.VOLUNTEER``).
"""

from datetime import date, datetime, timedelta

from application.utils.timezone import parse_eastern_datetime
from models import (
    Role,
    Tenant,
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


async def seed_volunteers_for_tenant(
    tenant: Tenant,
    users: dict[str, User],
    staff: User,
    today: date,
    now_utc: datetime,
) -> None:
    """Seed positions, opt-ins, qualifications, availability, shifts and one assignment."""
    await UserRole.get_or_create(
        user=staff, role=Role.VOLUNTEER_COORDINATOR, tenant=tenant, defaults={"granted_by": None},
    )

    position_specs = [
        ("Check-in Desk", 1, 1),
        ("Race Proctor", 2, 1),
        ("Broadcast Tech", 3, 3),  # multiple concurrent slots
        ("Admin Desk", 4, 1),
    ]
    positions: dict[str, VolunteerPosition] = {}
    default_slots: dict[str, int] = {}
    for name, order, slots in position_specs:
        p, _ = await VolunteerPosition.get_or_create(
            name=name, tenant=tenant, defaults={"display_order": order, "is_active": True},
        )
        positions[name] = p
        default_slots[name] = slots

    broadcast_tech = positions["Broadcast Tech"]
    if broadcast_tech.shift_length_minutes is None:
        broadcast_tech.shift_length_minutes = 240
        broadcast_tech.stagger_minutes = 120
        await broadcast_tech.save()

    # Notes are the free-text preferences the volunteer data export carries;
    # a few non-empty ones keep that column meaningful in dev.
    opted_in = {
        "proctor_user": "Happy to proctor all weekend. Please no Saturday morning.",
        "sm_user": "Can lift/carry gear; prefer to pair with someone on setup.",
        "player_one": "Available around my matches — check the schedule first.",
        "player_two": None,
        "player_three": "First time volunteering, would like a shadow shift.",
        # Deliberately absent from avail_specs below: the auto-scheduler's default
        # policy skips a volunteer who has not declared this time, and that skip
        # needs someone to skip.
        "player_four": "Can help wherever, ask me on the day.",
    }
    for uname, note in opted_in.items():
        profile, _ = await VolunteerProfile.get_or_create(user=users[uname], tenant=tenant)
        if profile.opted_in_at is None:
            profile.opted_in_at = now_utc
        if note and not profile.note:
            profile.note = note
        await profile.save()

    qual_specs = [
        ("proctor_user", "Race Proctor"),
        ("sm_user", "Broadcast Tech"),
        ("player_one", "Check-in Desk"),
        ("player_one", "Admin Desk"),
        ("player_two", "Race Proctor"),
    ]
    for uname, pos_name in qual_specs:
        await VolunteerQualification.get_or_create(
            user=users[uname], position=positions[pos_name], tenant=tenant,
        )

    event_days = [today + timedelta(days=d) for d in range(3)]
    avail_specs = {
        "proctor_user": ("08:00", "16:00", VolunteerAvailabilityStatus.PREFERRED),
        "sm_user": ("12:00", "20:00", VolunteerAvailabilityStatus.AVAILABLE),
        "player_one": ("08:00", "12:00", VolunteerAvailabilityStatus.AVAILABLE),
        "player_two": ("16:00", "00:00", VolunteerAvailabilityStatus.AVAILABLE),
        "player_three": ("08:00", "20:00", VolunteerAvailabilityStatus.AVAILABLE),
    }
    for uname, (start_hhmm, end_hhmm, status) in avail_specs.items():
        u = users[uname]
        if await VolunteerAvailability.filter(user=u, tenant=tenant).exists():
            continue
        for day in event_days:
            day_str = day.isoformat()
            starts_at = parse_eastern_datetime(day_str, start_hhmm)
            ends_at = parse_eastern_datetime(day_str, end_hhmm)
            if ends_at <= starts_at:
                ends_at = ends_at + timedelta(days=1)
            await VolunteerAvailability.create(
                user=u, starts_at=starts_at, ends_at=ends_at, status=status, tenant=tenant,
            )

    blocks = [
        ("Shift 1", "08:00", "12:00"),
        ("Shift 2", "12:00", "16:00"),
        ("Shift 3", "16:00", "20:00"),
        ("Shift 4", "20:00", "00:00"),
    ]
    shift_index: dict[tuple[str, str], VolunteerShift] = {}
    for day in event_days[:2]:
        day_str = day.isoformat()
        for pos_name, pos in positions.items():
            if pos.is_staggered:
                coverage_start = parse_eastern_datetime(day_str, blocks[0][1])
                coverage_end = parse_eastern_datetime(day_str, blocks[-1][2])
                if coverage_end <= coverage_start:
                    coverage_end = coverage_end + timedelta(days=1)
                length = timedelta(minutes=pos.shift_length_minutes)
                stagger = timedelta(minutes=pos.stagger_minutes)
                cursor = coverage_start
                while cursor < coverage_end:
                    await VolunteerShift.get_or_create(
                        position=pos, starts_at=cursor, tenant=tenant,
                        defaults={"ends_at": min(cursor + length, coverage_end),
                                  "slots_needed": 1},
                    )
                    cursor += stagger
                continue
            for label, start_hhmm, end_hhmm in blocks:
                starts_at = parse_eastern_datetime(day_str, start_hhmm)
                ends_at = parse_eastern_datetime(day_str, end_hhmm)
                if ends_at <= starts_at:
                    ends_at = ends_at + timedelta(days=1)
                shift, _ = await VolunteerShift.get_or_create(
                    position=pos, starts_at=starts_at, tenant=tenant,
                    defaults={
                        "ends_at": ends_at, "label": label,
                        "slots_needed": default_slots[pos_name],
                    },
                )
                shift_index[(day_str, f"{pos_name}|{label}")] = shift

    first_day = event_days[0].isoformat()
    proctor_shift = shift_index.get((first_day, "Race Proctor|Shift 1"))
    if proctor_shift:
        await VolunteerAssignment.get_or_create(
            shift=proctor_shift, user=users["proctor_user"], tenant=tenant,
            defaults={"assigned_by": staff},
        )

    second_day = event_days[1].isoformat()
    draft_shift = shift_index.get((second_day, "Check-in Desk|Shift 1"))
    if draft_shift:
        # An unpublished autoscheduler draft: outlined on the coordinator's grid,
        # invisible on the volunteer's page until Publish draft.
        await VolunteerAssignment.get_or_create(
            shift=draft_shift, user=users["player_three"], tenant=tenant,
            defaults={"assigned_by": staff, "auto_generated": True},
        )
    print(f"    [{tenant.slug}] volunteers ok")
