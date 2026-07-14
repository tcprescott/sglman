#!/usr/bin/env python3
"""Seed the dev database with test fixtures across **two** tenants.

Run from the project root:
    poetry run python scripts/seed_dev.py

Idempotent — safe to re-run; existing records are left unchanged.
Requires the schema to already exist (run ./start.sh dev or aerich upgrade first).

Users are global (no tenant FK): the same people log in everywhere and hold
per-tenant roles/memberships. Everything else is tenant-scoped, so the fixtures
are seeded once **per tenant** with ``tenant`` threaded through every scoped
create — giving leak tests and manual dev cross-tenant data from day one. Tenant
A adopts the ``default`` slug the migration backfills (created empty on a fresh
dev DB); tenant B is a second community.
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
    Tenant, TenantMembership,
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
    RacetimeBot,
)
from application.tenant_context import tenant_scope
from application.utils.timezone import now_eastern, parse_eastern_datetime
from scripts.seed_online import (
    link_racetime_identities, seed_racetime_bots, seed_online_for_tenant,
)


# Two dev tenants. Tenant A reuses the migration's ``default`` slug; on a fresh
# dev DB the backfill creates it empty and this adopts it.
TENANT_SPECS = [
    ("default", "SGL Default", 1000000000000000001, "a"),
    ("second", "Second Community", 1000000000000000002, "b"),
]


async def seed_users() -> dict[str, User]:
    """Create the global (tenant-agnostic) users. Roles are granted per tenant."""
    user_specs = [
        ("100000000000000001", "staff_user",   "Staff User"),
        ("100000000000000002", "proctor_user", "Proctor User"),
        ("100000000000000003", "sm_user",      "SM User"),
        ("100000000000000004", "player_one",   "Player One"),
        ("100000000000000005", "player_two",   "Player Two"),
        ("100000000000000006", "player_three", "Player Three"),
        ("100000000000000007", "player_four",  "Player Four"),
    ]
    users: dict[str, User] = {}
    for discord_id, username, display_name in user_specs:
        u, _ = await User.get_or_create(
            discord_id=discord_id,
            defaults={"username": username, "display_name": display_name, "is_active": True},
        )
        users[username] = u
    await link_racetime_identities(users)
    print("  users ok (global)")
    return users


async def seed_for_tenant(
    tenant: Tenant, users: dict[str, User], bots: dict[str, RacetimeBot]
) -> None:
    """Seed all tenant-scoped fixtures for one tenant.

    ``tenant`` is threaded through every scoped create/get_or_create (both the
    lookup and the row) so the data is isolated per tenant — the application
    threads tenant explicitly rather than through a global manager, and this
    script mirrors that contract.
    """
    with tenant_scope(tenant.id):
        # Every scoped user is a member of this tenant.
        for u in users.values():
            await TenantMembership.get_or_create(user=u, tenant=tenant)

        # Roles (per tenant)
        role_grants = [
            ("staff_user", Role.STAFF),
            ("proctor_user", Role.PROCTOR),
            ("sm_user", Role.STREAM_MANAGER),
            ("player_one", Role.TRIFORCE_SUBMITTER),
        ]
        for uname, role in role_grants:
            await UserRole.get_or_create(
                user=users[uname], role=role, tenant=tenant, defaults={"granted_by": None},
            )

        # Stream rooms
        for name, url in [
            ("Stage 1", "https://twitch.tv/sglive"),
            ("Stage 2", "https://twitch.tv/sglive2"),
            ("Stage 3", "https://twitch.tv/sglive3"),
        ]:
            await StreamRoom.get_or_create(
                name=name, tenant=tenant,
                defaults={"stream_url": url, "is_active": True},
            )
        print(f"    [{tenant.slug}] stream rooms ok")

        # System configuration
        today = now_eastern().date()
        for key, val in [
            ("event_start_date", today.isoformat()),
            ("event_end_date", (today + timedelta(days=2)).isoformat()),
            ("max_concurrent_players", "12"),
            ("max_concurrent_stages", "3"),
        ]:
            await SystemConfiguration.get_or_create(
                name=key, tenant=tenant, defaults={"value": val},
            )
        print(f"    [{tenant.slug}] system config ok")

        # Tournament
        staff = users["staff_user"]
        tournament, _ = await Tournament.get_or_create(
            name="SGL Dev Tournament", tenant=tenant,
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
            await TournamentPlayers.get_or_create(tournament=tournament, user=p, tenant=tenant)
        print(f"    [{tenant.slug}] tournament ok")

        # Matches — one per lifecycle state, plus extra fixtures for variety
        stage1 = await StreamRoom.get(name="Stage 1", tenant=tenant)
        stage2 = await StreamRoom.get(name="Stage 2", tenant=tenant)
        stage3 = await StreamRoom.get(name="Stage 3", tenant=tenant)
        now = now_eastern()

        async def make_match(
            title: str,
            offset_hours: float | None,
            *,
            seated: bool = False,
            started: bool = False,
            finished: bool = False,
            confirmed: bool = True,
            p1: User | None = None,
            p2: User | None = None,
            room: StreamRoom | None = None,
            stream_candidate: bool = True,
            comment: str | None = None,
        ) -> Match:
            scheduled_at = now + timedelta(hours=offset_hours) if offset_hours is not None else None
            match, created = await Match.get_or_create(
                title=title,
                tournament=tournament,
                tenant=tenant,
                defaults={
                    "scheduled_at": scheduled_at,
                    "stream_room": room,
                    "is_stream_candidate": stream_candidate,
                    "comment": comment,
                },
            )
            if not created:
                return match
            anchor = scheduled_at or now
            if seated or started or finished:
                match.seated_at = anchor - timedelta(minutes=10)
            if started or finished:
                match.started_at = anchor
            if finished:
                match.finished_at = anchor + timedelta(hours=1)
                if confirmed:
                    match.confirmed_at = anchor + timedelta(hours=1, minutes=5)
            await match.save()
            for rank, player in enumerate([p1, p2], 1):
                if player:
                    await MatchPlayers.get_or_create(
                        match=match,
                        user=player,
                        tenant=tenant,
                        defaults={"finish_rank": rank if finished else None},
                    )
            return match

        scheduled_match = await make_match("Scheduled Match",   2,   p1=players[0], p2=players[1])
        checked_in_match = await make_match("Checked-In Match",  0,   seated=True,  p1=players[0], p2=players[1], room=stage1)
        in_progress_match = await make_match("In-Progress Match", -1,  seated=True, started=True,  p1=players[2], p2=players[3], room=stage2)
        finished_match = await make_match("Finished Match",    -3,  seated=True, started=True, finished=True, p1=players[0], p2=players[2], room=stage1)
        stage3_match = await make_match(
            "Stage 3 Rematch", 3, seated=True, p1=players[1], p2=players[3], room=stage3,
            comment="Requested a rematch after a disconnect last round.",
        )
        offstream_match = await make_match(
            "Off-Stream Match", 4, p1=players[2], p2=players[0], stream_candidate=False,
        )
        future_match = await make_match(
            "Grand Finals", 30, p1=players[3], p2=players[1], room=stage1,
            comment="Best of 3, winner takes the trophy.",
        )
        disputed_match = await make_match(
            "Disputed Match", -5, seated=True, started=True, finished=True, confirmed=False,
            p1=players[1], p2=players[2], room=stage2,
            comment="Result under review — desync reported by both players.",
        )
        unscheduled_match = await make_match(
            "TBD Match", None, p1=players[3], p2=players[0], stream_candidate=False,
        )
        matches = {
            "scheduled": scheduled_match,
            "checked_in": checked_in_match,
            "in_progress": in_progress_match,
            "finished": finished_match,
            "stage3": stage3_match,
            "offstream": offstream_match,
            "future": future_match,
            "disputed": disputed_match,
            "unscheduled": unscheduled_match,
        }
        print(f"    [{tenant.slug}] matches ok")

        # Generated seeds, attached to matches that have already been rolled.
        seed, _ = await GeneratedSeeds.get_or_create(
            seed_url="https://alttpr.com/en/h/DevSeed0",
            tenant=tenant,
            defaults={"seed_info": json.dumps({"logic": "NoGlitches", "spoilers": "off"})},
        )
        if finished_match.generated_seed_id is None:
            finished_match.generated_seed = seed
            await finished_match.save()

        disputed_seed, _ = await GeneratedSeeds.get_or_create(
            seed_url="https://alttpr.com/en/h/DevSeed1",
            tenant=tenant,
            defaults={"seed_info": json.dumps({"logic": "Glitched", "spoilers": "mystery"})},
        )
        if disputed_match.generated_seed_id is None:
            disputed_match.generated_seed = disputed_seed
            await disputed_match.save()

        # Match acknowledgments — the checked-in match's players have both confirmed.
        for player in (players[0], players[1]):
            await MatchAcknowledgment.get_or_create(
                match=checked_in_match, user=player, tenant=tenant,
                defaults={"acknowledged_at": now, "auto_acknowledged": False},
            )
        # The scheduled match still has one un-acknowledged and one pending player.
        await MatchAcknowledgment.get_or_create(
            match=scheduled_match, user=players[0], tenant=tenant,
            defaults={"acknowledged_at": now, "auto_acknowledged": False},
        )
        await MatchAcknowledgment.get_or_create(
            match=scheduled_match, user=players[1], tenant=tenant,
            defaults={"acknowledged_at": None, "auto_acknowledged": False},
        )
        # Grand Finals — one player auto-acknowledged, the other hasn't responded.
        await MatchAcknowledgment.get_or_create(
            match=future_match, user=players[3], tenant=tenant,
            defaults={"acknowledged_at": now, "auto_acknowledged": True},
        )
        await MatchAcknowledgment.get_or_create(
            match=future_match, user=players[1], tenant=tenant,
            defaults={"acknowledged_at": None, "auto_acknowledged": False},
        )

        # Match watchers — staff keeps an eye on the scheduled, in-progress, and disputed matches.
        for m in (scheduled_match, in_progress_match, disputed_match):
            await MatchWatcher.get_or_create(user=staff, match=m, tenant=tenant)

        # Notification preference — staff wants DMs for every match in this tournament.
        await TournamentNotificationPreference.get_or_create(
            user=staff, tournament=tournament, tenant=tenant,
            defaults={"match_notifications": MatchNotificationLevel.ALL},
        )
        print(f"    [{tenant.slug}] match extras ok")

        # --- Online tournaments: presets, racetime config & rooms -----------
        # This wires ``tournament`` to a racetime.gg bot, so its matches now hide
        # the on-site check-in / station-assignment controls.
        await seed_online_for_tenant(
            tenant, tournament, scheduled_match, finished_match, bots
        )

        # --- On-site tournament (no racetime.gg) ----------------------------
        # A deliberately on-site tournament so the schedule keeps demonstrating
        # the check-in and station-assignment controls that the racetime-enabled
        # tournament above now hides.
        onsite, _ = await Tournament.get_or_create(
            name="SGL On-Site Cup", tenant=tenant,
            defaults={
                "description": "On-site fixture — no racetime.gg integration.",
                "seed_generator": "alttpr",
                "is_active": True,
                "players_per_match": 2,
                "staff_administered": False,
            },
        )
        await onsite.admins.add(staff)
        for p in (players[0], players[1]):
            await TournamentPlayers.get_or_create(tournament=onsite, user=p, tenant=tenant)

        onsite_match, onsite_created = await Match.get_or_create(
            title="On-Site Scheduled", tournament=onsite, tenant=tenant,
            defaults={
                "scheduled_at": now + timedelta(hours=2),
                "stream_room": stage1,
                "is_stream_candidate": True,
            },
        )
        if onsite_created:
            for p in (players[0], players[1]):
                await MatchPlayers.get_or_create(match=onsite_match, user=p, tenant=tenant)
        print(f"    [{tenant.slug}] on-site tournament ok")

        # --- Crew signups (commentators / trackers) -------------------------
        sm = users["sm_user"]
        proctor = users["proctor_user"]
        await Commentator.get_or_create(
            match=in_progress_match, user=sm, tenant=tenant,
            defaults={"approved": True, "approved_by": staff, "acknowledged_at": now},
        )
        await Tracker.get_or_create(
            match=in_progress_match, user=proctor, tenant=tenant,
            defaults={"approved": False},
        )
        await Commentator.get_or_create(
            match=finished_match, user=proctor, tenant=tenant,
            defaults={"approved": True, "approved_by": staff, "acknowledged_at": now - timedelta(hours=3)},
        )
        await Commentator.get_or_create(
            match=future_match, user=sm, tenant=tenant,
            defaults={"approved": True, "approved_by": staff, "acknowledged_at": now},
        )
        await Commentator.get_or_create(
            match=future_match, user=proctor, tenant=tenant,
            defaults={"approved": False},
        )
        await Tracker.get_or_create(
            match=stage3_match, user=sm, tenant=tenant,
            defaults={"approved": True, "approved_by": staff, "acknowledged_at": now},
        )
        print(f"    [{tenant.slug}] crew ok")

        # --- Volunteer scheduling -------------------------------------------
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

        opted_in = ["proctor_user", "sm_user", "player_one", "player_two", "player_three"]
        now_utc = datetime.now(timezone.utc)
        for uname in opted_in:
            profile, _ = await VolunteerProfile.get_or_create(user=users[uname], tenant=tenant)
            if profile.opted_in_at is None:
                profile.opted_in_at = now_utc
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
        print(f"    [{tenant.slug}] volunteers ok")

        # --- Player availability --------------------------------------------
        player_avail_specs = {
            "player_one": ("10:00", "18:00", VolunteerAvailabilityStatus.PREFERRED),
            "player_two": ("14:00", "22:00", VolunteerAvailabilityStatus.AVAILABLE),
            "player_three": ("08:00", "12:00", VolunteerAvailabilityStatus.AVAILABLE),
            "player_four": ("18:00", "23:00", VolunteerAvailabilityStatus.UNAVAILABLE),
        }
        for uname, (start_hhmm, end_hhmm, status) in player_avail_specs.items():
            u = users[uname]
            if await PlayerAvailability.filter(user=u, tenant=tenant).exists():
                continue
            for day in event_days:
                day_str = day.isoformat()
                starts_at = parse_eastern_datetime(day_str, start_hhmm)
                ends_at = parse_eastern_datetime(day_str, end_hhmm)
                if ends_at <= starts_at:
                    ends_at = ends_at + timedelta(days=1)
                await PlayerAvailability.create(
                    user=u, starts_at=starts_at, ends_at=ends_at, status=status, tenant=tenant,
                )
        print(f"    [{tenant.slug}] player availability ok")

        # --- Equipment lending ----------------------------------------------
        await UserRole.get_or_create(
            user=staff, role=Role.EQUIPMENT_MANAGER, tenant=tenant, defaults={"granted_by": None},
        )

        equipment_specs = [
            ("Capture Card A", "Elgato HD60 X", None),
            ("Capture Card B", "Elgato HD60 X", None),
            ("Console 1", "Super Nintendo (SNES)", staff),
            ("HDMI Splitter", "4-way powered splitter", None),
        ]
        equipment: dict[str, Equipment] = {}
        for name, description, owner in equipment_specs:
            asset = await Equipment.get_or_none(name=name, tenant=tenant)
            if asset is None:
                # asset_number is unique per tenant; take this tenant's max + 1.
                row = await Equipment.filter(tenant=tenant).annotate(m=Max("asset_number")).values("m")
                next_number = (row[0]["m"] or 0) + 1
                asset = await Equipment.create(
                    asset_number=next_number, name=name, description=description,
                    owner_user=owner, tenant=tenant,
                )
            equipment[name] = asset

        card_a = equipment["Capture Card A"]
        if not await EquipmentLoan.filter(equipment=card_a, tenant=tenant).exists():
            await EquipmentLoan.create(
                equipment=card_a, borrower=users["player_one"], checked_out_by=staff, tenant=tenant,
            )
            if card_a.status != EquipmentStatus.CHECKED_OUT:
                card_a.status = EquipmentStatus.CHECKED_OUT
                await card_a.save()

        console = equipment["Console 1"]
        if not await EquipmentLoan.filter(equipment=console, tenant=tenant).exists():
            await EquipmentLoan.create(
                equipment=console, borrower=users["player_two"], checked_out_by=staff,
                checked_in_at=now, checked_in_by=staff, tenant=tenant,
            )
        print(f"    [{tenant.slug}] equipment ok")

        # --- API tokens ------------------------------------------------------
        # Deterministic dev bearer strings, one pair per tenant, so REST
        # endpoints resolve to the right tenant. Non-secret fixtures; only the
        # SHA-256 hash is stored, exactly like production.
        dev_bearer = f"sglman_pat_devseed_{tenant.slug}_local_only_do_not_use"
        if not await ApiToken.filter(user=staff, name="Dev Seed Token", tenant=tenant).exists():
            await ApiToken.create(
                user=staff, name="Dev Seed Token", tenant=tenant,
                token_hash=hashlib.sha256(dev_bearer.encode()).hexdigest(),
                token_prefix=dev_bearer[:17], read_only=False,
            )
        ro_bearer = f"sglman_pat_devseedro_{tenant.slug}_local_only_do_not"
        if not await ApiToken.filter(user=staff, name="Dev Read-Only Token", tenant=tenant).exists():
            await ApiToken.create(
                user=staff, name="Dev Read-Only Token", tenant=tenant,
                token_hash=hashlib.sha256(ro_bearer.encode()).hexdigest(),
                token_prefix=ro_bearer[:17], read_only=True,
            )
        print(f"    [{tenant.slug}] api tokens ok (dev bearer: {dev_bearer})")

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
            if not await Feedback.filter(user=users[uname], message=message, tenant=tenant).exists():
                await Feedback.create(
                    user=users[uname], category=category, status=status,
                    message=message, page_url=page_url, tenant=tenant,
                )
        print(f"    [{tenant.slug}] feedback ok")

        # --- Triforce texts --------------------------------------------------
        triforce_specs = [
            ("player_one", "You found the Triforce of Courage!", "Player One", True),
            ("player_two", "The hero's spirit lives on.", "Player Two", None),
            ("player_three", "not a real submission", "Player Three", False),
        ]
        for uname, text, author, approved in triforce_specs:
            u = users[uname]
            if await TriforceText.filter(tournament=tournament, user=u, text=text, tenant=tenant).exists():
                continue
            await TriforceText.create(
                tournament=tournament, user=u, text=text, author=author,
                approved=approved,
                approved_by=staff if approved is not None else None,
                approved_at=now if approved is not None else None,
                tenant=tenant,
            )
        print(f"    [{tenant.slug}] triforce texts ok")

        # --- Discord role mappings ------------------------------------------
        # Each tenant maps its own guild's roles onto app roles.
        guild_id = tenant.discord_guild_id
        role_mapping_specs = [
            (2000000000000000001, "SGL Staff", Role.STAFF),
            (2000000000000000002, "Proctors", Role.PROCTOR),
            (2000000000000000003, "Stream Managers", Role.STREAM_MANAGER),
            (2000000000000000004, "Volunteers", Role.VOLUNTEER),
        ]
        for discord_role_id, discord_role_name, app_role in role_mapping_specs:
            await DiscordRoleMapping.get_or_create(
                guild_id=guild_id, discord_role_id=discord_role_id, app_role=app_role,
                tenant=tenant, defaults={"discord_role_name": discord_role_name},
            )
        print(f"    [{tenant.slug}] discord role mappings ok")

        # --- Challonge mirror ------------------------------------------------
        # Player identity is global (one-time capture); the connection/bracket
        # mirror is per tenant.
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
            tournament.challonge_tournament_id = f"cht_dev_{tenant.slug}"
            tournament.challonge_tournament_url = f"https://challonge.com/sgl_{tenant.slug}"
            tournament.challonge_last_synced_at = now_utc
            await tournament.save()

        # A near-expiry token so the service-health board / tenant subset (PR 5)
        # has a live credential-warning to render. Heal older rows that predate the
        # expiry column too, so a re-seed against an existing dev DB still shows it.
        challonge_expiry = now_utc + timedelta(days=2)
        conn, _ = await ChallongeConnection.get_or_create(
            challonge_username="sgl_service", tenant=tenant,
            defaults={
                "access_token": "dev-access-token-not-real",
                "refresh_token": "dev-refresh-token-not-real",
                "scopes": "me tournaments:read tournaments:write",
                "token_expires_at": challonge_expiry,
                "connected_by": staff,
            },
        )
        if conn.token_expires_at is None:
            conn.token_expires_at = challonge_expiry
            await conn.save()

        participants: dict[str, ChallongeParticipant] = {}
        participant_specs = [
            ("cp_1", "Player One", "cu_1001", users["player_one"]),
            ("cp_2", "Player Two", "cu_1002", users["player_two"]),
            ("cp_3", "Player Three", None, users["player_three"]),
            ("cp_4", "Player Four", None, users["player_four"]),
        ]
        for cp_id, name, challonge_uid, user in participant_specs:
            part, _ = await ChallongeParticipant.get_or_create(
                tournament=tournament, challonge_participant_id=cp_id, tenant=tenant,
                defaults={"name": name, "challonge_user_id": challonge_uid, "user": user},
            )
            participants[cp_id] = part

        await ChallongeMatch.get_or_create(
            tournament=tournament, challonge_match_id="cm_1", tenant=tenant,
            defaults={
                "round": 1, "state": ChallongeMatchState.COMPLETE,
                "participant1": participants["cp_1"], "participant2": participants["cp_3"],
                "winner_participant": participants["cp_1"], "match": matches["finished"],
            },
        )
        await ChallongeMatch.get_or_create(
            tournament=tournament, challonge_match_id="cm_2", tenant=tenant,
            defaults={
                "round": 1, "state": ChallongeMatchState.OPEN,
                "participant1": participants["cp_2"], "participant2": participants["cp_4"],
            },
        )

        usage_period = today.strftime("%Y-%m")
        await ChallongeApiUsage.get_or_create(
            period=usage_period, tenant=tenant, defaults={"request_count": 42},
        )
        print(f"    [{tenant.slug}] challonge ok")

        # --- Audit log -------------------------------------------------------
        audit_specs = [
            (staff, "tournament.created", {"tournament_id": tournament.id, "name": tournament.name}),
            (staff, "match.created", {"match_id": finished_match.id, "title": finished_match.title}),
            (staff, "match.finished", {"match_id": finished_match.id}),
            (staff, "user.role_granted", {"user_id": proctor.id, "role": Role.PROCTOR.value}),
            (staff, "equipment.checked_out", {"equipment_id": card_a.id, "borrower_id": users["player_one"].id}),
        ]
        if await AuditLog.filter(tenant=tenant).count() == 0:
            for actor, action, details in audit_specs:
                await AuditLog.create(
                    user=actor, action=action, details=json.dumps(details, sort_keys=True), tenant=tenant,
                )
        print(f"    [{tenant.slug}] audit log ok")


async def seed() -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        users = await seed_users()
        bots = await seed_racetime_bots()
        for slug, name, guild_id, _label in TENANT_SPECS:
            tenant, created = await Tenant.get_or_create(
                slug=slug, defaults={"name": name, "discord_guild_id": guild_id},
            )
            # The migration backfills the ``default`` tenant with the guild id
            # from config (NULL on a fresh dev DB); give it a dev guild so the
            # role-mapping fixtures below have a non-null guild to attach to.
            if tenant.discord_guild_id is None:
                tenant.discord_guild_id = guild_id
                await tenant.save()
            print(f"  tenant '{slug}' ({'created' if created else 'exists'}, id={tenant.id})")
            await seed_for_tenant(tenant, users, bots)
    finally:
        await Tortoise.close_connections()
    print("Seeding complete.")


asyncio.run(seed())
