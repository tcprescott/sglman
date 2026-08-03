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

from tortoise import Tortoise

from application.services.audit_service import AuditActions
from application.services.feature_flag_service import FeatureFlagService
from application.services.mcp_auth_service import READ_SCOPE, WRITE_SCOPE
from application.services.room_token_service import hash_token
from application.tenant_context import tenant_scope
from application.utils.timezone import now_local, parse_local_datetime
from models import (
    ApiToken,
    ApiTokenOrigin,
    AuditLog,
    DiscordRoleMapping,
    DiscordTournamentGrant,
    FeatureFlag,
    FeatureFlagGroup,
    JoinRequestStatus,
    McpOAuthClient,
    PlayerAvailability,
    RacetimeBot,
    Role,
    RoleSource,
    RoomToken,
    Stage,
    Station,
    StationSide,
    SystemConfiguration,
    Tenant,
    TenantFeatureFlag,
    TenantJoinRequest,
    TenantMembership,
    Tournament,
    TournamentGrant,
    TournamentPlayers,
    TriforceText,
    User,
    UserRole,
    VolunteerAvailabilityStatus,
)
from scripts.seed_brackets import seed_brackets_for_tenant
from scripts.seed_challonge import seed_challonge_for_tenant
from scripts.seed_crew import seed_crew_for_tenant
from scripts.seed_equipment import seed_equipment_for_tenant
from scripts.seed_fledgling import seed_fledgling_tenant
from scripts.seed_match_day import seed_match_day_for_tenant
from scripts.seed_matches import seed_matches_for_tenant
from scripts.seed_observability import seed_observability_for_tenant
from scripts.seed_online import (
    assert_unlinked_probe_users,
    link_racetime_identities,
    link_twitch_identities,
    reset_unlinked_probe_users,
    seed_online_for_tenant,
    seed_racetime_bots,
)
from scripts.seed_onsite import seed_onsite_for_tenant
from scripts.seed_payouts import seed_matcherino_handles, seed_payouts_for_tenant
from scripts.seed_play_in import seed_play_in_for_tenant
from scripts.seed_preferences import seed_table_preferences
from scripts.seed_support import (
    RACER_SPECS,
    USER_SPECS,
    backfill,
    fixture_discord_id,
)
from scripts.seed_volunteers import seed_volunteers_for_tenant

# Two dev tenants. Tenant A reuses the migration's ``default`` slug; on a fresh
# dev DB the backfill creates it empty and this adopts it. Tenant B carries a
# custom ``domain`` so host-based routing is exercisable locally: browsers
# resolve ``*.localhost`` to 127.0.0.1, so http://second.localhost:8000/ serves
# the second community with no /etc/hosts edit.
TENANT_SPECS = [
    ("default", "Wizzrobe Default", 1000000000000000001, "a", None),
    ("second", "Second Community", 1000000000000000002, "b", "second.localhost:8000"),
]


# Per-user display-timezone preferences. Only consulted by a community that
# leaves the choice to its members (tenant 'second'), so these are what make the
# profile-preference branch reachable in dev — and what makes a still-hardcoded
# Eastern render obvious, since none of them is Eastern. Everyone else keeps
# NULL, which means "detect from my device".
TIMEZONE_SPECS = {
    'player_one': 'Europe/Berlin',
    'player_two': 'Asia/Tokyo',
    'player_three': 'America/Los_Angeles',
    # A half-hour offset, which is what catches code assuming whole-hour zones.
    'player_four': 'Asia/Kolkata',
}


async def seed_timezone_preferences(users: dict[str, User]) -> None:
    """Give a few fixtures an explicit timezone; leave the rest on detection."""
    for username, zone in TIMEZONE_SPECS.items():
        u = users.get(username)
        if u is not None and u.timezone != zone:
            u.timezone = zone
            await u.save()


async def seed_users() -> dict[str, User]:
    """Create the global (tenant-agnostic) users. Roles are granted per tenant."""
    specs = [(name, display) for name, display in USER_SPECS]
    specs += [(name, display) for name, display, _ in RACER_SPECS]
    users: dict[str, User] = {}
    for username, display_name in specs:
        discord_id = fixture_discord_id(username)
        # Convergence for a dev database seeded before ids were derived: the row
        # is found by its username and re-pointed, so its matches, roles and
        # memberships follow it instead of a second copy of every fixture
        # appearing beside the first.
        legacy = await User.get_or_none(username=username)
        if legacy is not None and legacy.discord_id != discord_id:
            legacy.discord_id = discord_id
            await legacy.save()
        u, created = await User.get_or_create(
            discord_id=discord_id,
            defaults={"username": username, "display_name": display_name, "is_active": True},
        )
        # The discord id is the identity key; the name is fixture metadata, so a
        # renamed or renumbered fixture has to converge on re-seed rather than
        # leave the previous occupant of that id wearing the wrong name in every
        # dev picker.
        if not created and (u.username != username or u.display_name != display_name):
            u.username, u.display_name = username, display_name
            await u.save()
        users[username] = u
    await seed_timezone_preferences(users)
    await seed_matcherino_handles(users)
    await link_racetime_identities(users)
    await link_twitch_identities(users)
    # Before anything else writes a provider id: clicking Link as one of these
    # fixtures is what they exist for, so a re-seed restores them.
    await reset_unlinked_probe_users(users)
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
        for uname, u in users.items():
            # Every scoped user is a member of this tenant, bar the two fixtures
            # that exist to be absent: local_only is the "member of one community
            # and not another" case, outsider the "member of nothing at all" one,
            # which is what the membership gate's join page needs to be reachable
            # in dev.
            if uname == 'outsider' or (uname == 'local_only' and tenant.slug != 'default'):
                # Deleted, not merely skipped: these two fixtures are defined by
                # an *absence*, and a create-only seed can never converge one —
                # a stale row from an earlier fixture layout would leave them
                # members here and quietly stop proving anything.
                await TenantMembership.filter(user=u, tenant=tenant).delete()
                continue
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
            # One holder each for the three online-tournament admin roles, and
            # nothing else: the Presets tab, the sync config (SpeedGaming /
            # racetime / Discord events) and the qualifier review queue each gate
            # on one of these, and a surface that gates on staff-ness instead
            # looks correct until the delegate it was written for logs in.
            ("preset_mgr", Role.PRESET_MANAGER),
            ("sync_user", Role.SYNC_ADMIN),
            ("qual_admin", Role.QUALIFIER_ADMIN),
            # The same rule applied to the four roles whose only holders also held
            # VOLUNTEER (proctor_user, sm_user, player_one): with nothing holding
            # them alone, a surface that means to gate on PROCTOR but gates on
            # VOLUNTEER — or the reverse — passed in dev either way.
            ("proctor_only", Role.PROCTOR),
            ("sm_only", Role.STREAM_MANAGER),
            ("triforce_sub", Role.TRIFORCE_SUBMITTER),
            ("volunteer_only", Role.VOLUNTEER),
        ]
        if tenant.slug == "default":
            # Deliberately one tenant only — a role grant implies membership, so
            # a user who holds nothing in tenant B and is a member of nothing
            # there must be absent from tenant B's pickers.
            role_grants.append(("local_only", Role.VOLUNTEER))
        # Roles the guild-role sync granted rather than a staff member: the
        # DiscordRoleMapping fixtures below map this guild's "Volunteers" role
        # onto VOLUNTEER, and these are the rows that mapping would produce.
        # ``RoleSource`` is what the role table's "granted by" column reads, and
        # what a re-sync is allowed to revoke — a seed where every grant is
        # MANUAL cannot show either.
        discord_sourced = {("player_three", Role.VOLUNTEER), ("player_four", Role.VOLUNTEER)}
        for uname, role in role_grants:
            await UserRole.get_or_create(
                user=users[uname], role=role, tenant=tenant,
                defaults={
                    "granted_by": None,
                    "source": (
                        RoleSource.DISCORD if (uname, role) in discord_sourced
                        else RoleSource.MANUAL
                    ),
                },
            )
        print(
            f"    [{tenant.slug}] roles ok"
            + (" (local_only is a VOLUNTEER here and nowhere else)"
               if tenant.slug == "default" else " (local_only holds nothing here)")
        )

        # Stages
        for name, url in [
            ("Stage 1", "https://twitch.tv/wizzrobe"),
            ("Stage 2", "https://twitch.tv/wizzrobe2"),
            ("Stage 3", "https://twitch.tv/wizzrobe3"),
        ]:
            await Stage.get_or_create(
                name=name, tenant=tenant,
                defaults={"stream_url": url, "is_active": True},
            )
        print(f"    [{tenant.slug}] stages ok")

        # Venue station pool — two banks facing into the middle of the room.
        # Only tenant A defines one: a community with no stations keeps the
        # historical free-text station field, and tenant B is that fixture.
        if tenant.slug == "default":
            # Sided and numbered so the check-in draw has a room to work with:
            # six a side, neighbours one apart, more than the live matches
            # occupy. Station 13 has no layout — the "no side set" fixture.
            layout = (
                [(f"{n}", "North wall", StationSide.LEFT, n) for n in range(1, 7)]
                + [(f"{n}", "South wall", StationSide.RIGHT, n - 6) for n in range(7, 13)]
                + [("13", "Overflow", None, None)]
            )
            for idx, (nm, section, side, pos) in enumerate(layout):
                await Station.get_or_create(
                    name=nm, tenant=tenant,
                    defaults={"section": section, "side": side,
                              "position": pos, "sort_order": idx},
                )
            print(f"    [{tenant.slug}] stations ok")
        else:
            print(f"    [{tenant.slug}] stations skipped (free-text fallback fixture)")

        # System configuration — every key SystemConfigService reads, because a
        # key the seed omits is a Settings-tab field that reads as "not
        # configured" in dev and a code path (venue hours, the reminder lead, the
        # station-label format) that only ever runs on its fallback.
        today = now_local().date()
        event_days = [today + timedelta(days=d) for d in range(3)]
        venue_hours = {
            event_days[0].isoformat(): {"open": "10:00", "close": "23:00"},
            event_days[1].isoformat(): {"open": "09:00", "close": "23:00"},
            event_days[2].isoformat(): {"open": "09:00", "close": "20:00"},
        }
        config_specs = [
            ("event_start_date", today.isoformat()),
            ("event_end_date", (today + timedelta(days=2)).isoformat()),
            ("max_concurrent_players", "12"),
            ("max_concurrent_stages", "3"),
            ("volunteer_reminder_lead_minutes", "90"),
            ("volunteer_comp_tiers", "8, 12, 16"),
            ("tournament_hours_by_date", json.dumps(venue_hours, sort_keys=True)),
            # Tenant A's stations are the numbered pool seeded below, so it
            # enforces numeric labels; tenant B has no station pool and keeps the
            # free-text default — the two halves of the same setting.
            ("station_format", "numeric" if tenant.slug == "default" else "free"),
            # Both halves of the join-page preview: tenant B publishes today's
            # matches to non-members, tenant A keeps the gate closed. A dev
            # signed out of both sees the two versions of the same door.
            ("join_page_match_preview", "true" if tenant.slug == "second" else "false"),
        ]
        for key, val in config_specs:
            await SystemConfiguration.get_or_create(
                name=key, tenant=tenant, defaults={"value": val},
            )
        print(f"    [{tenant.slug}] system config ok")

        # Tournament
        staff = users["staff_user"]
        # The operational metadata a real tournament carries. Not decoration:
        # ``average_match_duration`` is what the suggestion engine spaces matches
        # by and what the reports' expected-average column reads (both fall back
        # to a hard-coded 90 when it is NULL, so dev could never tell the two
        # apart), and the format/rules links are what the player-facing header
        # renders.
        # The Tournaments tab reads three signup states off these columns, so the
        # seed has to produce all three: this one is **open** (window running
        # now), Wizzrobe Cup is **closed** (see seed_onsite), and the qualifier
        # below has not opened yet. Its description is markdown because the card
        # renders it through the safe-markdown renderer, and a plain sentence
        # would never exercise that path.
        dev_tournament_meta = {
            "tournament_format": "Double elimination, best of 3",
            "bracket_url": f"https://challonge.com/wizzrobe_{tenant.slug}",
            "rules_url": "https://example.invalid/wizzrobe/rules",
            "average_match_duration": 90,
            "max_match_duration": 150,
            "triforce_access_message": (
                "Submit your triforce text once you have played a match — "
                "approved texts go into the seeds we roll for finals."
            ),
        }
        dev_tournament_meta["signups_open_at"] = now_local() - timedelta(days=3)
        dev_tournament_meta["signups_close_at"] = now_local() + timedelta(days=14)
        tournament, _ = await Tournament.get_or_create(
            name="Wizzrobe Dev Tournament", tenant=tenant,
            defaults={
                "description": (
                    "Fixture tournament for local dev.\n\n"
                    "## Format\n\n"
                    "Double elimination, best of 3. Finals are best of 5.\n\n"
                    "- Sign up before the window closes\n"
                    "- Staff schedule your matches from the player pool\n"
                ),
                "seed_generator": "alttpr",
                "is_active": True,
                "players_per_match": 2,
                "staff_administered": False,
                **dev_tournament_meta,
            },
        )
        await backfill(tournament, **dev_tournament_meta)
        await tournament.admins.add(staff)
        await tournament.crew_coordinators.add(staff)
        await tournament.crew_coordinators.add(users["cc_user"])
        # Heal the fixture that the duplicated discord id left behind: cc_user
        # used to collide with `outsider` on id ...011, so a dev database seeded
        # before the fix holds this coordinator grant against the account that is
        # supposed to belong to no community at all.
        await tournament.crew_coordinators.remove(users["outsider"])

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
        stage1 = await Stage.get(name="Stage 1", tenant=tenant)
        stage2 = await Stage.get(name="Stage 2", tenant=tenant)
        stage3 = await Stage.get(name="Stage 3", tenant=tenant)
        now = now_local()

        fixtures = await seed_matches_for_tenant(
            tenant, tournament, staff, players,
            {"stage1": stage1, "stage2": stage2, "stage3": stage3}, now,
        )
        finished_match = fixtures["finished"]
        disputed_match = fixtures["disputed"]
        seed = fixtures["seed"]

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

        # --- Prize payouts (scripts/seed_payouts.py) -------------------------
        await seed_payouts_for_tenant(tenant, players)

        # --- Group play-in races (scripts/seed_play_in.py) -------------------
        # Staff-run races of ten, seeding the bracket above — the only rosters
        # longer than two, and the only match holding finishers and forfeits
        # together. They belong to this tournament because that is the bracket
        # they feed.
        racers = players + [users[name] for name, _display, _full in RACER_SPECS]
        await seed_play_in_for_tenant(tenant, tournament, staff, racers, now)

        # --- One realistic match day (scripts/seed_match_day.py) -------------
        # Density, not states: fifteen ordinary bracket matches across the three
        # stages so the schedule and the stage-utilisation report have a real day
        # to draw. Everything it creates is deliberately unremarkable.
        await seed_match_day_for_tenant(
            tenant, tournament, racers, [stage1, stage2, stage3], today, now,
        )

        # --- Crew signups (scripts/seed_crew.py) ----------------------------
        sm = users["sm_user"]
        proctor = users["proctor_user"]
        await seed_crew_for_tenant(
            tenant, staff, sm, proctor, players, fixtures, now,
        )
        print(f"    [{tenant.slug}] crew ok")

        # --- Volunteer scheduling (scripts/seed_volunteers.py) ---------------
        now_utc = datetime.now(timezone.utc)
        await seed_volunteers_for_tenant(tenant, users, staff, today, now_utc)

        # --- Player availability --------------------------------------------
        # Same three-day window the venue hours and the volunteer fixtures use.
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
                starts_at = parse_local_datetime(day_str, start_hhmm)
                ends_at = parse_local_datetime(day_str, end_hhmm)
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

        # --- Tournament room screens -----------------------------------------
        # A live token per tenant plus a revoked one, so the settings list shows
        # both states and /ui-validation can open the seeds board without a
        # login. Deterministic like the bearers above and just as non-secret.
        room_token = f"wizzrobe_room_devseed_{tenant.slug}_local_only_do_not_use"
        await RoomToken.get_or_create(
            token_hash=hash_token(room_token),
            defaults={"label": "Room A desk PC", "tenant": tenant, "created_by": staff},
        )
        await RoomToken.get_or_create(
            token_hash=hash_token(f"{room_token}_retired"),
            defaults={
                "label": "Old laptop (retired)", "tenant": tenant,
                "created_by": staff, "revoked_at": now,
            },
        )
        print(f"    [{tenant.slug}] room tokens ok (/room/{room_token}/seeds)")


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
        # The other shape of mapping: a guild role onto one tournament's grants
        # rather than a community-wide role. Both live in the same table and the
        # admin tab renders them side by side, so the seed needs one of each.
        for discord_role_id, discord_role_name, grant in [
            (2000000000000000005, "Event Admins", TournamentGrant.TOURNAMENT_ADMIN),
            (2000000000000000006, "Crew Leads", TournamentGrant.CREW_COORDINATOR),
        ]:
            await DiscordRoleMapping.get_or_create(
                guild_id=guild_id, discord_role_id=discord_role_id,
                tournament_grant=grant, tournament=tournament, tenant=tenant,
                defaults={"discord_role_name": discord_role_name},
            )
        # And the provenance rows sync would leave behind, so the "a re-sync may
        # take this back" state sits next to a hand-made grant that it may not:
        # staff holds both grants manually, these two came from the guild roles.
        for uname, grant in [
            ("player_three", TournamentGrant.CREW_COORDINATOR),
            ("player_four", TournamentGrant.TOURNAMENT_ADMIN),
        ]:
            relation = (
                tournament.admins if grant == TournamentGrant.TOURNAMENT_ADMIN
                else tournament.crew_coordinators
            )
            await relation.add(users[uname])
            await DiscordTournamentGrant.get_or_create(
                tournament=tournament, user=users[uname], grant=grant,
                defaults={"tenant": tenant},
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
        await seed_observability_for_tenant(tenant, staff, finished_match, now_utc, users)

        # --- Audit log -------------------------------------------------------
        # One row per action a staff member actually takes on a match day, so the
        # Audit tab's action filter has more than one value to filter by.
        audit_specs = [
            (staff, AuditActions.TOURNAMENT_CREATED,
             {"tournament_id": tournament.id, "name": tournament.name}),
            (staff, AuditActions.MATCH_CREATED,
             {"match_id": finished_match.id, "title": finished_match.title}),
            (staff, AuditActions.MATCH_SEED_ROLLED,
             {"match_id": finished_match.id, "randomizer": "alttpr",
              "preset": None, "seed_url": seed.seed_url}),
            (staff, AuditActions.MATCH_FINISHED, {"match_id": finished_match.id}),
            (staff, AuditActions.MATCH_FLAGGED_FOR_REVIEW,
             {"match_id": disputed_match.id}),
            (staff, AuditActions.USER_ROLE_GRANTED,
             {"user_id": proctor.id, "role": Role.PROCTOR.value}),
            (staff, AuditActions.EQUIPMENT_CHECKED_OUT,
             {"equipment_id": equipment["Capture Card A"].id, "borrower_id": users["player_one"].id}),
        ]
        # Per-row, not "only when the log is empty": anything else that writes an
        # audit row first — a preset import, a bracket created through its
        # service — would otherwise suppress this whole fixture set.
        for actor, action, details in audit_specs:
            payload = json.dumps(details, sort_keys=True)
            if not await AuditLog.filter(action=action, details=payload, tenant=tenant).exists():
                await AuditLog.create(
                    user=actor, action=action, details=payload, tenant=tenant,
                )
        print(f"    [{tenant.slug}] audit log ok")

        # A *decided* join request, so every state of the model exists in dev: the
        # pending one lives in 'fledgling' (the staff queue), this denied one is
        # the re-openable case — asking again updates this row rather than
        # appending a second — and the approved one is the ordinary outcome, the
        # record of how most members actually got in.
        await TenantJoinRequest.get_or_create(
            user=users['outsider'], tenant=tenant,
            defaults={
                'status': JoinRequestStatus.DENIED,
                'message': 'Can I get in?',
                'decided_by': staff,
                'decided_at': now_local(),
            },
        )
        await TenantJoinRequest.get_or_create(
            user=users['volunteer_only'], tenant=tenant,
            defaults={
                'status': JoinRequestStatus.APPROVED,
                'message': 'I commentate for a couple of events and would like to help.',
                'decided_by': staff,
                'decided_at': now_local() - timedelta(days=3),
            },
        )
        print(f"    [{tenant.slug}] join requests ok")



async def seed_mcp_oauth(users: dict[str, User]) -> None:
    """Seed a registered MCP client and two deterministic dev OAuth tokens.

    Global, like the users above: an OAuth grant belongs to no community. The
    tokens let /api-validation and manual curl runs exercise ``/mcp`` without
    driving the whole browser-based authorization flow, exactly as the dev PAT
    strings do for the REST API. Non-secret fixtures; only hashes are stored.

    Two of them, because the surface a token sees depends on the consent
    decision behind it: the read-only bearer is served the read tools alone,
    the writing one is served those plus the match writes. A single seeded
    token would leave half the server unreachable from a dev loop.

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
    grants = (
        ("Dev Seed MCP Token", "wizzrobe_mcp_devseed_local_only_do_not_use",
         "wizzrobe_mcpref_devseed_local_only_do_not_use", True, READ_SCOPE),
        ("Dev Seed MCP Write Token", "wizzrobe_mcp_devseedwrite_local_only_do_not_use",
         "wizzrobe_mcpref_devseedwrite_local_only_do_not_use", False,
         f"{READ_SCOPE} {WRITE_SCOPE}"),
    )
    for name, oauth_bearer, refresh_bearer, read_only, scope in grants:
        if not await ApiToken.filter(user=staff, name=name).exists():
            now = datetime.now(timezone.utc)
            await ApiToken.create(
                user=staff, name=name, tenant=None,
                oauth_client=client, origin=ApiTokenOrigin.OAUTH.value,
                read_only=read_only, scope=scope,
                token_hash=hashlib.sha256(oauth_bearer.encode()).hexdigest(),
                token_prefix=oauth_bearer[:17],
                expires_at=now + timedelta(days=3650),
                refresh_token_hash=hashlib.sha256(refresh_bearer.encode()).hexdigest(),
                refresh_expires_at=now + timedelta(days=3650),
            )
        kind = "read-only" if read_only else "write"
        print(f"  mcp oauth ok (global; {kind} dev bearer: {oauth_bearer})")


# seed-exempt: McpAuthorizationCode — ephemeral single-use rows minted mid-flow
# and consumed seconds later; a seeded one would always be stale/expired.


async def seed_all() -> None:
    """Seed everything into the already-initialized ORM connection.

    Split from ``seed()`` so the pytest suite can run the full seed against its
    own in-memory connection — see tests/test_seed_coverage.py.
    """
    users = await seed_users()
    await seed_super_admin(users)
    await seed_table_preferences(users)
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
        # One community of each timezone mode, so both paths are reachable in a
        # dev environment without touching the admin UI first. Tenant A pins
        # Eastern (the on-site SpeedGaming Live shape, and what the migration
        # gives every existing community); tenant B follows each member's own
        # clock with a non-US default, which is the shape online tournaments
        # need and the one that catches "still hardcoded to Eastern".
        tz_settings = (
            {'mode': 'pinned', 'name': 'America/New_York'} if slug == 'default'
            else {'mode': 'user', 'name': 'Europe/London'}
        )
        if (tenant.config or {}).get('timezone') != tz_settings:
            config = dict(tenant.config or {})
            config['timezone'] = tz_settings
            tenant.config = config
            await tenant.save()
        print(f"  tenant '{slug}' ({'created' if created else 'exists'}, id={tenant.id})")
        # Tier first: the per-tenant fixtures below consult the live flags (a
        # service that enforces a flag refuses to seed data for a tenant that
        # lacks the feature), so availability has to be settled before seeding.
        await assign_feature_group(tenant, groups)
        await seed_for_tenant(tenant, users, bots)
    await seed_fledgling_tenant(users, groups)
    # Last, because the per-tenant Challonge mirror above also links identities:
    # the unlinked fixtures have to be unlinked after everything that could link
    # them has run.
    await assert_unlinked_probe_users(users)


async def seed() -> None:
    # Lazy, both of them: building TORTOISE_ORM requires DB_* env vars, and
    # importing this module must stay env-free so tests can import seed_all.
    # load_dotenv() at import time was not env-free — it pushed the dev .env
    # (MOCK_DISCORD, MOCK_SEEDGEN) into os.environ for the whole pytest worker,
    # so any later test on that worker silently ran in mock mode.
    from dotenv import load_dotenv
    load_dotenv()

    from migrations.tortoise_config import TORTOISE_ORM

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        await seed_all()
    finally:
        await Tortoise.close_connections()
    print("Seeding complete.")


if __name__ == "__main__":
    asyncio.run(seed())
