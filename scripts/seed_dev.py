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

from tortoise import Tortoise
from tortoise.functions import Max
from models import (
    Tenant, TenantMembership, TenantFeatureFlag, FeatureFlagGroup, FeatureFlag,
    User, UserRole, Role,
    Tournament, TournamentPlayers,
    Match, MatchPlayers, MatchAcknowledgment, MatchWatcher,
    Commentator, Tracker, GeneratedSeeds,
    TournamentNotificationPreference, MatchNotificationLevel,
    Station, StreamRoom, SystemConfiguration,
    ApiToken, ApiTokenOrigin, McpOAuthClient,
    Feedback, FeedbackCategory, FeedbackStatus,
    Equipment, EquipmentLoan, EquipmentStatus,
    AuditLog, DiscordRoleMapping, TriforceText, PlayerAvailability,
    VolunteerAvailabilityStatus,
    RacetimeBot,
)
from application.tenant_context import tenant_scope
from application.services.feature_flag_service import FeatureFlagService
from application.utils.timezone import now_eastern, parse_eastern_datetime
from scripts.seed_brackets import seed_brackets_for_tenant
from scripts.seed_challonge import seed_challonge_for_tenant
from scripts.seed_equipment import seed_equipment_for_tenant
from scripts.seed_observability import seed_observability_for_tenant
from scripts.seed_onsite import seed_onsite_for_tenant
from scripts.seed_volunteers import seed_volunteers_for_tenant
from scripts.seed_online import (
    link_racetime_identities, seed_racetime_bots, seed_online_for_tenant,
)


# Two dev tenants. Tenant A reuses the migration's ``default`` slug; on a fresh
# dev DB the backfill creates it empty and this adopts it. Tenant B carries a
# custom ``domain`` so host-based routing is exercisable locally: browsers
# resolve ``*.localhost`` to 127.0.0.1, so http://second.localhost:8000/ serves
# the second community with no /etc/hosts edit.
TENANT_SPECS = [
    ("default", "Wizzrobe Default", 1000000000000000001, "a", None),
    ("second", "Second Community", 1000000000000000002, "b", "second.localhost:8000"),
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
        # Deliberately granted no *tenant* role anywhere (see seed_super_admin):
        # the dev fixture for "platform authority, zero local grants", which is
        # what /platform and the super-admin's in-tenant access need to be
        # exercised against.
        ("100000000000000008", "super_admin",  "Platform Owner"),
        # EQUIPMENT_MANAGER *without* STAFF (granted per tenant below).
        # staff_user holds both, so nothing else proves the manager path works
        # on its own — three audits had to grant a role like this by hand.
        ("100000000000000009", "equip_manager", "Equipment Manager"),
        # Granted a role in the 'default' tenant only (see seed_for_tenant), and
        # enrolled in nothing: the fixture that makes per-community people
        # scoping visible in the dev loop. They must appear in tenant A's
        # borrower/owner pickers and in neither of tenant B's.
        ("100000000000000010", "local_only",   "Local Only"),
        # Two more single-capability operators, for the same reason as
        # equip_manager: staff satisfies every predicate in the admin area, so a
        # surface that gates on staff-ness where it means to gate on a
        # capability looks correct until one of these logs in.
        ("100000000000000011", "cc_user",      "Crew Coordinator"),
        ("100000000000000012", "vc_user",      "Volunteer Coordinator"),
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


async def seed_super_admin(users: dict[str, User]) -> None:
    """Grant the global ``SUPER_ADMIN`` role (``UserRole`` with ``tenant=NULL``).

    Granted outside ``seed_for_tenant`` because the row is deliberately
    tenant-less, and to no other seeded user — the point of the fixture is a
    platform admin whose authority in each community comes *only* from this role,
    so ``/platform`` and the cross-tenant admin paths are reachable in dev.
    """
    await UserRole.get_or_create(
        user=users['super_admin'], role=Role.SUPER_ADMIN, tenant=None,
        defaults={'granted_by': None},
    )
    print('  super admin ok (global, tenant=NULL)')


async def seed_feature_groups() -> dict:
    """Create the demo feature-flag groups (tiers). Idempotent by name.

    Migration 31 already creates 'Default' (empty, is_default) and 'Online
    Tournaments'; this also ensures a 'Full Access' tier for dev and returns all
    three keyed by role.
    """
    default, _ = await FeatureFlagGroup.get_or_create(
        name='Default',
        defaults={
            'description': 'Live fallback for tenants with no group assigned.',
            'flags': [], 'is_default': True,
        },
    )
    # update_or_create for the two demo tiers: migration 31 seeds 'Online
    # Tournaments' with the flags that existed *then*, so a get_or_create would
    # leave any flag added (or retired) since out of the tier this claims to
    # define. Group contents are a super-admin's editable data in production —
    # the migration is right not to rewrite them there — but in dev the seed is
    # the fixture set and gets to be authoritative.
    online, _ = await FeatureFlagGroup.update_or_create(
        name='Online Tournaments',
        defaults={'flags': ['async_qualifiers', 'racetime_rooms', 'speedgaming_etl']},
    )
    full, _ = await FeatureFlagGroup.update_or_create(
        name='Full Access',
        defaults={'flags': [f.value for f in FeatureFlag]},
    )
    print('  feature groups ok (Default / Online Tournaments / Full Access)')
    return {'default': default, 'online': online, 'full': full}


async def assign_feature_group(tenant: Tenant, groups: dict) -> None:
    """Assign a dev tenant to a tier plus one demo override.

    Tenant A → Full Access (everything live), with one feature the community has
    switched OFF (sticky enable override). Tenant B → Online Tournaments, with one
    extra feature force-granted as a per-tenant availability exception. Together
    they exercise group-derived, community-disabled, and override states.
    """
    # update_or_create, not get_or_create: migration 32 backfills every
    # ``established`` flag as available+enabled for pre-existing tenants, so a
    # get_or_create finds that row and silently keeps the demo state it means to
    # set — the community-opted-out case then never exists in dev.
    if tenant.slug == 'default':
        tenant.feature_group = groups['full']
        await tenant.save()
        await TenantFeatureFlag.update_or_create(
            tenant=tenant, flag=FeatureFlag.TRIFORCE_TEXTS.value,
            defaults={'available': None, 'enabled': False},  # community opted out
        )
    else:
        tenant.feature_group = groups['online']
        await tenant.save()
        await TenantFeatureFlag.update_or_create(
            tenant=tenant, flag=FeatureFlag.EQUIPMENT.value,
            defaults={'available': True, 'enabled': None},  # per-tenant exception
        )
    print(f"    [{tenant.slug}] feature tier ok")


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

        # Roles (per tenant). The VOLUNTEER grants below mirror the opted-in +
        # qualified + available pool seeded further down so the Vol. Roster tab and
        # the auto-scheduler actually have an assignable pool to show
        # (VolunteerProfileService.assignable_volunteers filters on Role.VOLUNTEER).
        role_grants = [
            ("staff_user", Role.STAFF),
            ("proctor_user", Role.PROCTOR),
            ("sm_user", Role.STREAM_MANAGER),
            ("player_one", Role.TRIFORCE_SUBMITTER),
            ("proctor_user", Role.VOLUNTEER),
            ("sm_user", Role.VOLUNTEER),
            ("player_one", Role.VOLUNTEER),
            ("player_two", Role.VOLUNTEER),
            ("player_three", Role.VOLUNTEER),
            ("player_four", Role.VOLUNTEER),
            # Deliberately the only grant vc_user gets: a coordinator with no
            # staff role. cc_user gets no role row at all — crew coordination is
            # a per-tournament relation, granted below.
            ("vc_user", Role.VOLUNTEER_COORDINATOR),
        ]
        if tenant.slug == "default":
            # Deliberately one tenant only — the per-community people read
            # derives membership from grants like this one, so a user who holds
            # nothing in tenant B must be absent from tenant B's pickers.
            role_grants.append(("local_only", Role.VOLUNTEER))
        for uname, role in role_grants:
            await UserRole.get_or_create(
                user=users[uname], role=role, tenant=tenant, defaults={"granted_by": None},
            )
        print(
            f"    [{tenant.slug}] roles ok"
            + (" (local_only is a VOLUNTEER here and nowhere else)"
               if tenant.slug == "default" else " (local_only holds nothing here)")
        )

        # Stream rooms
        for name, url in [
            ("Stage 1", "https://twitch.tv/wizzrobe"),
            ("Stage 2", "https://twitch.tv/wizzrobe2"),
            ("Stage 3", "https://twitch.tv/wizzrobe3"),
        ]:
            await StreamRoom.get_or_create(
                name=name, tenant=tenant,
                defaults={"stream_url": url, "is_active": True},
            )
        print(f"    [{tenant.slug}] stream rooms ok")

        # Venue station pool — two banks facing into the middle of the room.
        # Only tenant A defines one: a community with no stations keeps the
        # historical free-text station field, and tenant B is the fixture for
        # that fallback path.
        if tenant.slug == "default":
            for idx, (station_name, section) in enumerate(
                [(f"{n}", "North wall") for n in range(1, 5)]
                + [(f"{n}", "South wall") for n in range(5, 9)]
            ):
                await Station.get_or_create(
                    name=station_name, tenant=tenant,
                    defaults={"section": section, "sort_order": idx},
                )
            print(f"    [{tenant.slug}] stations ok")
        else:
            print(f"    [{tenant.slug}] stations skipped (free-text fallback fixture)")

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
            name="Wizzrobe Dev Tournament", tenant=tenant,
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
        await tournament.crew_coordinators.add(users["cc_user"])

        # The general-purpose fixture tournament is deliberately **on-premises**:
        # its matches are the proctor-lifecycle fixtures, and attaching a
        # racetime.gg bot hides every on-site control on them (and drops them
        # from the Proctor Station board). Racetime lives on its own tournament
        # now (scripts/seed_online.py), so a dev database seeded before the split
        # gets that wiring cleared here.
        if tournament.racetime_bot_id is not None or tournament.discord_events_enabled:
            tournament.racetime_bot = None
            tournament.racetime_auto_create_rooms = False
            tournament.discord_events_enabled = False
            await tournament.save()

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
        await make_match(
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
        await make_match(
            "TBD Match", None, p1=players[3], p2=players[0], stream_candidate=False,
        )
        # Seat the two matches that are checked in but not finished at real
        # stations, so the schedule shows stations out of the box and the
        # occupancy check has something to trip on: 1/2/5/6 read as in use when
        # a proctor opens the picker on any other match.
        for seated_match, labels in (
            (checked_in_match, ("1", "5")),
            (in_progress_match, ("2", "6")),
        ):
            seated_players = await MatchPlayers.filter(
                match=seated_match, tenant=tenant,
            ).order_by("id")
            for seated_player, label in zip(seated_players, labels):
                if seated_player.assigned_station is None and tenant.slug == "default":
                    seated_player.assigned_station = label
                    await seated_player.save()

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

        # The dispute flag itself, so the admin's review queue has a contested
        # row out of the box — this match has claimed to be disputed since the
        # first seed script and only now actually is.
        if not disputed_match.needs_review:
            disputed_match.needs_review = True
            disputed_match.review_note = (
                "Player Two says the timer was still running when Player Three "
                "raised their hand. Needs an admin to look at the VOD."
            )
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

        # --- Online tournament (scripts/seed_online.py) ----------------------
        # Its own racetime.gg-managed tournament with its own matches, kept apart
        # from the tournament above: a racetime bot hides every on-site control
        # on the matches it owns, so the two fixtures cannot share a tournament.
        await seed_online_for_tenant(tenant, staff, players, bots)

        # --- Second on-site tournament (scripts/seed_onsite.py) --------------
        # A distinct venue event with its own "tournament days" override and one
        # match per step of the proctor's workflow.
        await seed_onsite_for_tenant(tenant, staff, players, today, now, stage1, stage3)
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

        # --- Volunteer scheduling (scripts/seed_volunteers.py) ---------------
        now_utc = datetime.now(timezone.utc)
        await seed_volunteers_for_tenant(tenant, users, staff, today, now_utc)

        # --- Player availability --------------------------------------------
        # Same three-day window the volunteer fixtures use.
        event_days = [today + timedelta(days=d) for d in range(3)]
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

        # --- Equipment lending (scripts/seed_equipment.py) -------------------
        equipment = await seed_equipment_for_tenant(tenant, users, staff, now)

        # --- API tokens ------------------------------------------------------
        # Deterministic dev bearer strings, one pair per tenant, so REST
        # endpoints resolve to the right tenant. Non-secret fixtures; only the
        # SHA-256 hash is stored, exactly like production.
        dev_bearer = f"wizzrobe_pat_devseed_{tenant.slug}_local_only_do_not_use"
        if not await ApiToken.filter(user=staff, name="Dev Seed Token", tenant=tenant).exists():
            await ApiToken.create(
                user=staff, name="Dev Seed Token", tenant=tenant,
                token_hash=hashlib.sha256(dev_bearer.encode()).hexdigest(),
                token_prefix=dev_bearer[:17], read_only=False,
            )
        ro_bearer = f"wizzrobe_pat_devseedro_{tenant.slug}_local_only_do_not"
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
             "Schedule times looked off on mobile.", "/home/schedule"),
            ("player_two", FeedbackCategory.SUGGESTION, FeedbackStatus.REVIEWED,
             "Would love a dark mode toggle.", "/"),
            ("sm_user", FeedbackCategory.PRAISE, FeedbackStatus.NEW,
             "The new crew view is great, thanks!", "/admin/schedule"),
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
            (2000000000000000001, "Wizzrobe Staff", Role.STAFF),
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

        # --- Challonge mirror (scripts/seed_challonge.py) --------------------
        await seed_challonge_for_tenant(
            tenant, users, tournament, staff, finished_match, now_utc, today,
        )

        # --- Native brackets (scripts/seed_brackets.py) ----------------------
        # Seeded through BracketService, which enforces FeatureFlag.BRACKETS, so a
        # tenant whose tier lacks the feature gets no bracket rows — which is the
        # coherent fixture state anyway (bracket data in a community that cannot
        # see brackets was only ever confusing). Tenant A carries the flag, so
        # every bracket model is still covered.
        if await FeatureFlagService().is_enabled(FeatureFlag.BRACKETS):
            await seed_brackets_for_tenant(tenant, tournament, users)
        else:
            print(f"    [{tenant.slug}] brackets skipped (feature not live)")


        # --- Webhooks + telemetry (scripts/seed_observability.py) -------------
        await seed_observability_for_tenant(tenant, staff, finished_match, now_utc)

        # --- Audit log -------------------------------------------------------
        audit_specs = [
            (staff, "tournament.created", {"tournament_id": tournament.id, "name": tournament.name}),
            (staff, "match.created", {"match_id": finished_match.id, "title": finished_match.title}),
            (staff, "match.finished", {"match_id": finished_match.id}),
            (staff, "user.role_granted", {"user_id": proctor.id, "role": Role.PROCTOR.value}),
            (staff, "equipment.checked_out",
             {"equipment_id": equipment["Capture Card A"].id, "borrower_id": users["player_one"].id}),
        ]
        if await AuditLog.filter(tenant=tenant).count() == 0:
            for actor, action, details in audit_specs:
                await AuditLog.create(
                    user=actor, action=action, details=json.dumps(details, sort_keys=True), tenant=tenant,
                )
        print(f"    [{tenant.slug}] audit log ok")



async def seed_mcp_oauth(users: dict[str, User]) -> None:
    """Seed a registered MCP client and a deterministic dev OAuth token.

    Global, like the users above: an OAuth grant belongs to no community. The
    token lets /api-validation and manual curl runs exercise ``/mcp`` without
    driving the whole browser-based authorization flow, exactly as the dev PAT
    strings do for the REST API. Non-secret fixtures; only hashes are stored.

    ``McpAuthorizationCode`` is deliberately not seeded — see below.
    """
    client, _ = await McpOAuthClient.get_or_create(
        client_id="devseed-local-client",
        defaults={
            "client_name": "Dev Seed MCP Client",
            "redirect_uris": ["http://127.0.0.1:6274/oauth/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    staff = users["staff_user"]
    oauth_bearer = "wizzrobe_mcp_devseed_local_only_do_not_use"
    refresh_bearer = "wizzrobe_mcpref_devseed_local_only_do_not_use"
    if not await ApiToken.filter(user=staff, name="Dev Seed MCP Token").exists():
        now = datetime.now(timezone.utc)
        await ApiToken.create(
            user=staff, name="Dev Seed MCP Token", tenant=None,
            oauth_client=client, origin=ApiTokenOrigin.OAUTH.value, read_only=True,
            token_hash=hashlib.sha256(oauth_bearer.encode()).hexdigest(),
            token_prefix=oauth_bearer[:17],
            expires_at=now + timedelta(days=3650),
            refresh_token_hash=hashlib.sha256(refresh_bearer.encode()).hexdigest(),
            refresh_expires_at=now + timedelta(days=3650),
        )
    print(f"  mcp oauth ok (global; dev bearer: {oauth_bearer})")


# seed-exempt: McpAuthorizationCode — ephemeral single-use rows minted mid-flow
# and consumed seconds later; a seeded one would always be stale/expired.


async def seed_all() -> None:
    """Seed everything into the already-initialized ORM connection.

    Split from ``seed()`` so the pytest suite can run the full seed against its
    own in-memory connection — see tests/test_seed_coverage.py.
    """
    users = await seed_users()
    await seed_super_admin(users)
    await seed_mcp_oauth(users)
    bots = await seed_racetime_bots()
    groups = await seed_feature_groups()
    for slug, name, guild_id, _label, domain in TENANT_SPECS:
        tenant, created = await Tenant.get_or_create(
            slug=slug,
            defaults={"name": name, "discord_guild_id": guild_id, "domain": domain},
        )
        # The migration backfills the ``default`` tenant with the guild id
        # from config (NULL on a fresh dev DB); give it a dev guild so the
        # role-mapping fixtures below have a non-null guild to attach to.
        if tenant.discord_guild_id is None:
            tenant.discord_guild_id = guild_id
            await tenant.save()
        # Idempotently adopt the custom domain (e.g. on a pre-existing dev DB).
        if domain and tenant.domain != domain:
            tenant.domain = domain
            await tenant.save()
        # Give the "second" community a custom brand palette so /ui-validation
        # and dev environments exercise the per-tenant theme path — the Ocean
        # preset, which reads clearly against the default gold/ember.
        if slug == 'second':
            from application.services.tenant_theme_service import THEME_PRESETS
            theme = dict(THEME_PRESETS['Ocean'])
            if (tenant.config or {}).get('theme') != theme:
                config = dict(tenant.config or {})
                config['theme'] = theme
                tenant.config = config
                await tenant.save()
        print(f"  tenant '{slug}' ({'created' if created else 'exists'}, id={tenant.id})")
        # Tier first: the per-tenant fixtures below consult the live flags (a
        # service that enforces a flag refuses to seed data for a tenant that
        # lacks the feature), so availability has to be settled before seeding.
        await assign_feature_group(tenant, groups)
        await seed_for_tenant(tenant, users, bots)


async def seed() -> None:
    # Lazy: building TORTOISE_ORM requires DB_* env vars, and importing this
    # module must stay env-free so tests can import seed_all.
    from migrations.tortoise_config import TORTOISE_ORM

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        await seed_all()
    finally:
        await Tortoise.close_connections()
    print("Seeding complete.")


if __name__ == "__main__":
    asyncio.run(seed())
