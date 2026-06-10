#!/usr/bin/env python3
"""Seed the dev database with test fixtures.

Run from the project root:
    poetry run python scripts/seed_dev.py

Idempotent — safe to re-run; existing records are left unchanged.
Requires the schema to already exist (run ./start.sh dev or aerich upgrade first).
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure project root is on the path when run as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from migrations.tortoise_config import TORTOISE_ORM
from tortoise import Tortoise
from models import (
    User, UserRole, Role,
    Tournament, TournamentPlayers,
    Match, MatchPlayers,
    StreamRoom, SystemConfiguration,
    VolunteerPosition, VolunteerProfile, VolunteerShift,
    VolunteerAssignment, VolunteerQualification,
    VolunteerAvailability, VolunteerAvailabilityStatus,
)
from application.utils.timezone import now_eastern, parse_eastern_datetime


async def seed() -> None:
    await Tortoise.init(config=TORTOISE_ORM)

    # Stream rooms
    for name, url in [
        ("Stage 1", "https://twitch.tv/sglive"),
        ("Stage 2", "https://twitch.tv/sglive2"),
        ("Stage 3", "https://twitch.tv/sglive3"),
    ]:
        await StreamRoom.get_or_create(name=name, defaults={"stream_url": url, "is_active": True})
    print("  stream rooms ok")

    # System configuration
    today = now_eastern().date()
    for key, val in [
        ("event_start_date", today.isoformat()),
        ("event_end_date", (today + timedelta(days=2)).isoformat()),
        ("max_concurrent_players", "12"),
        ("max_concurrent_stages", "3"),
    ]:
        await SystemConfiguration.get_or_create(name=key, defaults={"value": val})
    print("  system config ok")

    # Users and roles
    user_specs = [
        ("100000000000000001", "staff_user",   "Staff User",   Role.STAFF),
        ("100000000000000002", "proctor_user", "Proctor User", Role.PROCTOR),
        ("100000000000000003", "sm_user",      "SM User",      Role.STREAM_MANAGER),
        ("100000000000000004", "player_one",   "Player One",   Role.TRIFORCE_SUBMITTER),
        ("100000000000000005", "player_two",   "Player Two",   None),
        ("100000000000000006", "player_three", "Player Three", None),
        ("100000000000000007", "player_four",  "Player Four",  None),
    ]
    users: dict[str, User] = {}
    for discord_id, username, display_name, role in user_specs:
        u, _ = await User.get_or_create(
            discord_id=discord_id,
            defaults={"username": username, "display_name": display_name, "is_active": True},
        )
        users[username] = u
        if role:
            await UserRole.get_or_create(user=u, role=role, defaults={"granted_by": None})
    print("  users ok")

    # Tournament
    staff = users["staff_user"]
    tournament, _ = await Tournament.get_or_create(
        name="SGL Dev Tournament",
        defaults={
            "description": "Fixture tournament for local dev",
            "seed_generator": "alttpr",
            "is_active": True,
            "players_per_match": 2,
            "staff_administered": False,
        },
    )
    await tournament.admins.add(staff)
    await tournament.crew_coordinators.add(staff)

    players = [users[k] for k in ("player_one", "player_two", "player_three", "player_four")]
    for p in players:
        await TournamentPlayers.get_or_create(tournament=tournament, user=p)
    print("  tournament ok")

    # Matches — one per lifecycle state
    stage1 = await StreamRoom.get(name="Stage 1")
    stage2 = await StreamRoom.get(name="Stage 2")
    now = now_eastern()

    async def make_match(
        title: str,
        offset_hours: float,
        *,
        seated: bool = False,
        started: bool = False,
        finished: bool = False,
        p1: User | None = None,
        p2: User | None = None,
        room: StreamRoom | None = None,
    ) -> Match:
        scheduled_at = now + timedelta(hours=offset_hours)
        match, created = await Match.get_or_create(
            title=title,
            tournament=tournament,
            defaults={"scheduled_at": scheduled_at, "stream_room": room, "is_stream_candidate": True},
        )
        if not created:
            return match
        if seated or started or finished:
            match.seated_at = scheduled_at - timedelta(minutes=10)
        if started or finished:
            match.started_at = scheduled_at
        if finished:
            match.finished_at = scheduled_at + timedelta(hours=1)
            match.confirmed_at = scheduled_at + timedelta(hours=1, minutes=5)
        await match.save()
        for rank, player in enumerate([p1, p2], 1):
            if player:
                await MatchPlayers.get_or_create(
                    match=match,
                    user=player,
                    defaults={"finish_rank": rank if finished else None},
                )
        return match

    await make_match("Scheduled Match",   2,   p1=players[0], p2=players[1])
    await make_match("Checked-In Match",  0,   seated=True,  p1=players[0], p2=players[1], room=stage1)
    await make_match("In-Progress Match", -1,  seated=True, started=True,  p1=players[2], p2=players[3], room=stage2)
    await make_match("Finished Match",    -3,  seated=True, started=True, finished=True, p1=players[0], p2=players[2], room=stage1)
    print("  matches ok")

    # --- Volunteer scheduling -------------------------------------------
    # Staff coordinates; several users become opted-in volunteers.
    await UserRole.get_or_create(user=staff, role=Role.VOLUNTEER_COORDINATOR, defaults={"granted_by": None})
    volunteer_usernames = [
        "proctor_user", "sm_user", "player_one", "player_two", "player_three", "player_four",
    ]
    for uname in volunteer_usernames:
        await UserRole.get_or_create(user=users[uname], role=Role.VOLUNTEER, defaults={"granted_by": None})

    # Positions (arbitrary, coordinator-defined)
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
            name=name, defaults={"display_order": order, "is_active": True},
        )
        positions[name] = p
        default_slots[name] = slots

    # Opt-in profiles (player_four stays opted-out to exercise the gate)
    opted_in = ["proctor_user", "sm_user", "player_one", "player_two", "player_three"]
    now_utc = datetime.now(timezone.utc)
    for uname in opted_in:
        profile, _ = await VolunteerProfile.get_or_create(user=users[uname])
        if profile.opted_in_at is None:
            profile.opted_in_at = now_utc
            await profile.save()

    # Qualifications — some declare specific positions; player_three stays a generalist.
    qual_specs = [
        ("proctor_user", "Race Proctor"),
        ("sm_user", "Broadcast Tech"),
        ("player_one", "Check-in Desk"),
        ("player_one", "Admin Desk"),
        ("player_two", "Race Proctor"),
    ]
    for uname, pos_name in qual_specs:
        await VolunteerQualification.get_or_create(user=users[uname], position=positions[pos_name])

    # Availability windows across the event days (seeded once per user).
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
        if await VolunteerAvailability.filter(user=u).exists():
            continue
        for day in event_days:
            day_str = day.isoformat()
            starts_at = parse_eastern_datetime(day_str, start_hhmm)
            ends_at = parse_eastern_datetime(day_str, end_hhmm)
            if ends_at <= starts_at:
                ends_at = ends_at + timedelta(days=1)
            await VolunteerAvailability.create(
                user=u, starts_at=starts_at, ends_at=ends_at, status=status,
            )

    # Shifts: four 4-hour blocks per position for the first two event days.
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
            for label, start_hhmm, end_hhmm in blocks:
                starts_at = parse_eastern_datetime(day_str, start_hhmm)
                ends_at = parse_eastern_datetime(day_str, end_hhmm)
                if ends_at <= starts_at:
                    ends_at = ends_at + timedelta(days=1)
                shift, _ = await VolunteerShift.get_or_create(
                    position=pos, starts_at=starts_at,
                    defaults={
                        "ends_at": ends_at, "label": label,
                        "slots_needed": default_slots[pos_name],
                    },
                )
                shift_index[(day_str, f"{pos_name}|{label}")] = shift

    # One manual assignment to demonstrate a filled slot.
    first_day = event_days[0].isoformat()
    proctor_shift = shift_index.get((first_day, "Race Proctor|Shift 1"))
    if proctor_shift:
        await VolunteerAssignment.get_or_create(
            shift=proctor_shift, user=users["proctor_user"],
            defaults={"assigned_by": staff},
        )
    print("  volunteers ok")

    await Tortoise.close_connections()
    print("Seeding complete.")


asyncio.run(seed())
