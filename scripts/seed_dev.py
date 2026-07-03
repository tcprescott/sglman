#!/usr/bin/env python3
"""Seed the dev database with test fixtures.

Run from the project root:
    poetry run python scripts/seed_dev.py

Idempotent — safe to re-run; existing records are left unchanged.
Requires the schema to already exist (run ./start.sh dev or aerich upgrade first).
"""
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure project root is on the path when run as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from migrations.tortoise_config import TORTOISE_ORM
from tortoise import Tortoise
from tortoise.functions import Max
from models import (
    User, UserRole, Role,
    Tournament, TournamentPlayers,
    Match, MatchPlayers, MatchAcknowledgment, MatchWatcher,
    Commentator, Tracker, GeneratedSeeds,
    TournamentNotificationPreference, MatchNotificationLevel,
    StreamRoom, SystemConfiguration,
    ApiToken, Feedback, FeedbackCategory, FeedbackStatus,
    Equipment, EquipmentLoan, EquipmentStatus,
    AuditLog, DiscordRoleMapping, TriforceText, PlayerAvailability,
    ChallongeConnection, ChallongeParticipant, ChallongeMatch, ChallongeMatchState,
    ChallongeApiUsage,
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

    scheduled_match = await make_match("Scheduled Match",   2,   p1=players[0], p2=players[1])
    checked_in_match = await make_match("Checked-In Match",  0,   seated=True,  p1=players[0], p2=players[1], room=stage1)
    in_progress_match = await make_match("In-Progress Match", -1,  seated=True, started=True,  p1=players[2], p2=players[3], room=stage2)
    finished_match = await make_match("Finished Match",    -3,  seated=True, started=True, finished=True, p1=players[0], p2=players[2], room=stage1)
    matches = {
        "scheduled": scheduled_match,
        "checked_in": checked_in_match,
        "in_progress": in_progress_match,
        "finished": finished_match,
    }
    print("  matches ok")

    # A generated seed, attached to the finished match.
    seed, _ = await GeneratedSeeds.get_or_create(
        seed_url="https://alttpr.com/en/h/DevSeed0",
        defaults={"seed_info": json.dumps({"logic": "NoGlitches", "spoilers": "off"})},
    )
    if finished_match.generated_seed_id is None:
        finished_match.generated_seed = seed
        await finished_match.save()

    # Match acknowledgments — the checked-in match's players have both confirmed.
    for player in (players[0], players[1]):
        await MatchAcknowledgment.get_or_create(
            match=checked_in_match, user=player,
            defaults={"acknowledged_at": now, "auto_acknowledged": False},
        )
    # The scheduled match still has one un-acknowledged and one pending player.
    await MatchAcknowledgment.get_or_create(
        match=scheduled_match, user=players[0],
        defaults={"acknowledged_at": now, "auto_acknowledged": False},
    )
    await MatchAcknowledgment.get_or_create(
        match=scheduled_match, user=players[1],
        defaults={"acknowledged_at": None, "auto_acknowledged": False},
    )

    # Match watchers — staff keeps an eye on the scheduled and in-progress matches.
    for m in (scheduled_match, in_progress_match):
        await MatchWatcher.get_or_create(user=staff, match=m)

    # Notification preference — staff wants DMs for every match in this tournament.
    await TournamentNotificationPreference.get_or_create(
        user=staff, tournament=tournament,
        defaults={"match_notifications": MatchNotificationLevel.ALL},
    )
    print("  match extras ok")

    # --- Crew signups (commentators / trackers) -------------------------
    sm = users["sm_user"]
    proctor = users["proctor_user"]
    # In-progress match has an approved commentator and a pending tracker.
    await Commentator.get_or_create(
        match=in_progress_match, user=sm,
        defaults={"approved": True, "approved_by": staff, "acknowledged_at": now},
    )
    await Tracker.get_or_create(
        match=in_progress_match, user=proctor,
        defaults={"approved": False},
    )
    # Finished match kept its confirmed crew for history.
    await Commentator.get_or_create(
        match=finished_match, user=proctor,
        defaults={"approved": True, "approved_by": staff, "acknowledged_at": now - timedelta(hours=3)},
    )
    print("  crew ok")

    # --- Volunteer scheduling -------------------------------------------
    # Staff coordinates; any logged-in user can opt in to volunteer.
    await UserRole.get_or_create(user=staff, role=Role.VOLUNTEER_COORDINATOR, defaults={"granted_by": None})

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

    # Broadcast Tech rotates a rolling crew: 4h shifts starting every 2h, so the
    # techs hand off one at a time instead of all ending together.
    broadcast_tech = positions["Broadcast Tech"]
    if broadcast_tech.shift_length_minutes is None:
        broadcast_tech.shift_length_minutes = 240
        broadcast_tech.stagger_minutes = 120
        await broadcast_tech.save()

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
            if pos.is_staggered:
                # Rolling windows across the same overall day span (08:00–00:00).
                coverage_start = parse_eastern_datetime(day_str, blocks[0][1])
                coverage_end = parse_eastern_datetime(day_str, blocks[-1][2])
                if coverage_end <= coverage_start:
                    coverage_end = coverage_end + timedelta(days=1)
                length = timedelta(minutes=pos.shift_length_minutes)
                stagger = timedelta(minutes=pos.stagger_minutes)
                cursor = coverage_start
                while cursor < coverage_end:
                    await VolunteerShift.get_or_create(
                        position=pos, starts_at=cursor,
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

    # --- Player availability --------------------------------------------
    # Players self-declare windows they can be scheduled to race (mirrors the
    # volunteer availability shape, but for the competitive side).
    player_avail_specs = {
        "player_one": ("10:00", "18:00", VolunteerAvailabilityStatus.PREFERRED),
        "player_two": ("14:00", "22:00", VolunteerAvailabilityStatus.AVAILABLE),
        "player_three": ("08:00", "12:00", VolunteerAvailabilityStatus.AVAILABLE),
        "player_four": ("18:00", "23:00", VolunteerAvailabilityStatus.UNAVAILABLE),
    }
    for uname, (start_hhmm, end_hhmm, status) in player_avail_specs.items():
        u = users[uname]
        if await PlayerAvailability.filter(user=u).exists():
            continue
        for day in event_days:
            day_str = day.isoformat()
            starts_at = parse_eastern_datetime(day_str, start_hhmm)
            ends_at = parse_eastern_datetime(day_str, end_hhmm)
            if ends_at <= starts_at:
                ends_at = ends_at + timedelta(days=1)
            await PlayerAvailability.create(
                user=u, starts_at=starts_at, ends_at=ends_at, status=status,
            )
    print("  player availability ok")

    # --- Equipment lending ----------------------------------------------
    # Give staff the manager role so the equipment tab is exercisable.
    await UserRole.get_or_create(user=staff, role=Role.EQUIPMENT_MANAGER, defaults={"granted_by": None})

    equipment_specs = [
        ("Capture Card A", "Elgato HD60 X", None),
        ("Capture Card B", "Elgato HD60 X", None),
        ("Console 1", "Super Nintendo (SNES)", staff),
        ("HDMI Splitter", "4-way powered splitter", None),
    ]
    equipment: dict[str, Equipment] = {}
    for name, description, owner in equipment_specs:
        asset = await Equipment.get_or_none(name=name)
        if asset is None:
            row = await Equipment.annotate(m=Max("asset_number")).values("m")
            next_number = (row[0]["m"] or 0) + 1
            asset = await Equipment.create(
                asset_number=next_number, name=name, description=description, owner_user=owner,
            )
        equipment[name] = asset

    # An open loan (asset currently checked out) and a closed loan (history).
    card_a = equipment["Capture Card A"]
    if not await EquipmentLoan.filter(equipment=card_a).exists():
        await EquipmentLoan.create(
            equipment=card_a, borrower=users["player_one"], checked_out_by=staff,
        )
        if card_a.status != EquipmentStatus.CHECKED_OUT:
            card_a.status = EquipmentStatus.CHECKED_OUT
            await card_a.save()

    console = equipment["Console 1"]
    if not await EquipmentLoan.filter(equipment=console).exists():
        await EquipmentLoan.create(
            equipment=console, borrower=users["player_two"], checked_out_by=staff,
            checked_in_at=now, checked_in_by=staff,
        )
    print("  equipment ok")

    # --- API tokens ------------------------------------------------------
    # Deterministic dev bearer strings so REST endpoints are exercisable
    # locally. These are non-secret fixtures, regenerated on every seed of a
    # fresh DB; only their SHA-256 hash is stored, exactly like production.
    dev_bearer = "sglman_pat_devseedbearer_local_only_do_not_use_in_prod"
    if not await ApiToken.filter(user=staff, name="Dev Seed Token").exists():
        await ApiToken.create(
            user=staff, name="Dev Seed Token",
            token_hash=hashlib.sha256(dev_bearer.encode()).hexdigest(),
            token_prefix=dev_bearer[:17], read_only=False,
        )
    ro_bearer = "sglman_pat_devseedreadonly_local_only_do_not_use"
    if not await ApiToken.filter(user=staff, name="Dev Read-Only Token").exists():
        await ApiToken.create(
            user=staff, name="Dev Read-Only Token",
            token_hash=hashlib.sha256(ro_bearer.encode()).hexdigest(),
            token_prefix=ro_bearer[:17], read_only=True,
        )
    print(f"  api tokens ok (dev bearer: {dev_bearer})")

    # --- Feedback --------------------------------------------------------
    feedback_specs = [
        ("player_one", FeedbackCategory.BUG, FeedbackStatus.NEW,
         "Schedule times looked off on mobile.", "/?tab=schedule"),
        ("player_two", FeedbackCategory.SUGGESTION, FeedbackStatus.REVIEWED,
         "Would love a dark mode toggle.", "/"),
        ("sm_user", FeedbackCategory.PRAISE, FeedbackStatus.NEW,
         "The new crew view is great, thanks!", "/admin?tab=schedule"),
    ]
    for uname, category, status, message, page_url in feedback_specs:
        if not await Feedback.filter(user=users[uname], message=message).exists():
            await Feedback.create(
                user=users[uname], category=category, status=status,
                message=message, page_url=page_url,
            )
    print("  feedback ok")

    # --- Triforce texts --------------------------------------------------
    # One approved, one pending (approved is null), one rejected.
    triforce_specs = [
        ("player_one", "You found the Triforce of Courage!", "Player One", True),
        ("player_two", "The hero's spirit lives on.", "Player Two", None),
        ("player_three", "not a real submission", "Player Three", False),
    ]
    for uname, text, author, approved in triforce_specs:
        u = users[uname]
        if await TriforceText.filter(tournament=tournament, user=u, text=text).exists():
            continue
        await TriforceText.create(
            tournament=tournament, user=u, text=text, author=author,
            approved=approved,
            approved_by=staff if approved is not None else None,
            approved_at=now if approved is not None else None,
        )
    print("  triforce texts ok")

    # --- Discord role mappings ------------------------------------------
    dev_guild_id = 1000000000000000001
    role_mapping_specs = [
        (2000000000000000001, "SGL Staff", Role.STAFF),
        (2000000000000000002, "Proctors", Role.PROCTOR),
        (2000000000000000003, "Stream Managers", Role.STREAM_MANAGER),
        (2000000000000000004, "Volunteers", Role.VOLUNTEER),
    ]
    for discord_role_id, discord_role_name, app_role in role_mapping_specs:
        await DiscordRoleMapping.get_or_create(
            guild_id=dev_guild_id, discord_role_id=discord_role_id, app_role=app_role,
            defaults={"discord_role_name": discord_role_name},
        )
    print("  discord role mappings ok")

    # --- Challonge mirror ------------------------------------------------
    # Link a couple of players to a Challonge identity so bracket sync resolves.
    for uname, challonge_uid, challonge_name in [
        ("player_one", "cu_1001", "playerone"),
        ("player_two", "cu_1002", "playertwo"),
    ]:
        u = users[uname]
        if u.challonge_user_id is None:
            u.challonge_user_id = challonge_uid
            u.challonge_username = challonge_name
            u.challonge_linked_at = now_utc
            await u.save()

    if not tournament.challonge_tournament_id:
        tournament.challonge_tournament_id = "cht_dev_0001"
        tournament.challonge_tournament_url = "https://challonge.com/sgl_dev"
        tournament.challonge_last_synced_at = now_utc
        await tournament.save()

    await ChallongeConnection.get_or_create(
        challonge_username="sgl_service",
        defaults={
            "access_token": "dev-access-token-not-real",
            "refresh_token": "dev-refresh-token-not-real",
            "scopes": "me tournaments:read tournaments:write",
            "connected_by": staff,
        },
    )

    participants: dict[str, ChallongeParticipant] = {}
    participant_specs = [
        ("cp_1", "Player One", "cu_1001", users["player_one"]),
        ("cp_2", "Player Two", "cu_1002", users["player_two"]),
        ("cp_3", "Player Three", None, users["player_three"]),
        ("cp_4", "Player Four", None, users["player_four"]),
    ]
    for cp_id, name, challonge_uid, user in participant_specs:
        part, _ = await ChallongeParticipant.get_or_create(
            tournament=tournament, challonge_participant_id=cp_id,
            defaults={"name": name, "challonge_user_id": challonge_uid, "user": user},
        )
        participants[cp_id] = part

    # A complete match (linked to the finished sglman match) and an open one.
    await ChallongeMatch.get_or_create(
        tournament=tournament, challonge_match_id="cm_1",
        defaults={
            "round": 1, "state": ChallongeMatchState.COMPLETE,
            "participant1": participants["cp_1"], "participant2": participants["cp_3"],
            "winner_participant": participants["cp_1"], "match": matches["finished"],
        },
    )
    await ChallongeMatch.get_or_create(
        tournament=tournament, challonge_match_id="cm_2",
        defaults={
            "round": 1, "state": ChallongeMatchState.OPEN,
            "participant1": participants["cp_2"], "participant2": participants["cp_4"],
        },
    )

    usage_period = today.strftime("%Y-%m")
    await ChallongeApiUsage.get_or_create(period=usage_period, defaults={"request_count": 42})
    print("  challonge ok")

    # --- Audit log -------------------------------------------------------
    # A few representative entries so the audit view isn't empty. ``details``
    # is a JSON string, matching AuditService's on-disk format.
    audit_specs = [
        (staff, "tournament.created", {"tournament_id": tournament.id, "name": tournament.name}),
        (staff, "match.created", {"match_id": finished_match.id, "title": finished_match.title}),
        (staff, "match.finished", {"match_id": finished_match.id}),
        (staff, "user.role_granted", {"user_id": proctor.id, "role": Role.PROCTOR.value}),
        (staff, "equipment.checked_out", {"equipment_id": card_a.id, "borrower_id": users["player_one"].id}),
    ]
    if await AuditLog.all().count() == 0:
        for actor, action, details in audit_specs:
            await AuditLog.create(user=actor, action=action, details=json.dumps(details, sort_keys=True))
    print("  audit log ok")

    await Tortoise.close_connections()
    print("Seeding complete.")


asyncio.run(seed())
