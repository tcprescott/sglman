"""Dev-seed fixtures for the online-tournament features (PRs 1-10).

Split out of ``seed_dev.py`` to keep that file under the length guideline. These
functions are called from ``seed_dev.py`` — they assume an open Tortoise
connection and (for the per-tenant helper) an active ``tenant_scope``.

The per-tenant helper owns a **dedicated racetime.gg-managed tournament** rather
than wiring the general-purpose "Wizzrobe Dev Tournament" to a bot. Attaching a
bot flips ``Tournament.is_racetime_enabled``, which hides every on-site proctor
control (check-in, stations, start, finish) on that tournament's matches and
drops them from the Proctor Station board — so a tournament cannot be both the
racetime fixture and the proctor-lifecycle fixture.

What they cover:

- **Presets** (PR 1) — per-tenant ``Preset`` rows, one assigned to the online
  tournament, plus placeholder ``RandomizerCredential`` rows for keyed backends.
- **Racetime identity** (PR 2) — two players linked to racetime handles.
- **Racetime bots** (PR 3/4) — platform-level (no tenant FK), one connected and
  one parked in an error state so the ``/platform`` health table shows both.
- **Racetime config + rooms** (PR 3/4/6) — the online tournament's bot +
  auto-open config, its own matches, a room profile, and one race room per room
  lifecycle state.
- **SpeedGaming ETL** (PR 7), **Discord Events mirror** (PR 8) and **async
  qualifiers** (PR 9/10), all hanging off the same online tournament.
"""
from datetime import datetime, timedelta, timezone

from application.randomizer_credentials import all_specs, credentials_for
from models import (
    User, Tenant, TenantMembership, Tournament, Match, MatchPlayers, TournamentPlayers,
    Preset, RandomizerCredential,
    RacetimeBot, RacetimeBotTenant, RacetimeRoom, RaceRoomProfile,
    SpeedGamingEventLink, SpeedGamingEpisode, SyncStatus,
    DiscordScheduledEvent, DiscordEventSource,
    BotStatus, RaceRoomStatus,
    AsyncQualifier, AsyncQualifierPool, AsyncQualifierPermalink, AsyncQualifierRun,
    AsyncQualifierRunStatus, AsyncQualifierReviewStatus, AsyncQualifierReviewNote,
    AsyncQualifierLiveRace, AsyncQualifierLiveRaceStatus,
)
from application.utils.timezone import now_eastern

ONLINE_TOURNAMENT_NAME = "Wizzrobe Online Series"


async def link_racetime_identities(users: dict[str, User]) -> None:
    """Link two players to racetime handles (PR 2).

    Deliberately grants no roles. This used to also make ``staff_user`` a global
    SUPER_ADMIN "so /platform is reachable in dev", which left the one user the
    validation loop drives admin views as indistinguishable from a platform
    admin — every staff-vs-super-admin difference silently untestable. The
    dedicated ``super_admin`` fixture (``seed_dev.seed_super_admin``) covers
    /platform instead.
    """
    racetime_links = [
        ("player_one", "aBcDeFg1", "PlayerOne"),
        ("player_two", "hIjKlMn2", "PlayerTwo"),
    ]
    for key, rt_id, rt_name in racetime_links:
        u = users[key]
        if u.racetime_user_id is None:
            u.racetime_user_id = rt_id
            u.racetime_username = rt_name
            u.racetime_linked_at = now_eastern()
            await u.save()


async def seed_racetime_bots() -> dict[str, RacetimeBot]:
    """Platform-level racetime bots (PR 3/4). Bots have no tenant FK — they are
    managed at ``/platform`` and authorized per tenant. Seed one healthy,
    connected bot plus one in an error state so the /platform health table shows
    both variants."""
    now = now_eastern()
    alttpr, _ = await RacetimeBot.get_or_create(
        category="alttpr",
        defaults={
            "client_id": "dev_alttpr_client_id",
            "client_secret": "dev_alttpr_client_secret_local_only",
            "name": "ALTTPR Dev Bot",
            "description": "Fixture racetime bot for local dev (MOCK_RACETIME).",
            "is_active": True,
            "status": BotStatus.CONNECTED,
            "status_message": "Connected (mock transport).",
            "last_connected_at": now,
            "last_checked_at": now,
        },
    )
    await RacetimeBot.get_or_create(
        category="smw",
        defaults={
            "client_id": "dev_smw_client_id",
            "client_secret": "dev_smw_client_secret_local_only",
            "name": "SMW Dev Bot",
            "description": "Second fixture bot, parked in an error state.",
            "is_active": True,
            "status": BotStatus.ERROR,
            "status_message": "Authentication rejected (fixture).",
            "last_checked_at": now,
        },
    )
    print("  racetime bots ok (global)")
    return {"alttpr": alttpr}


async def seed_online_for_tenant(
    tenant: Tenant,
    staff: User,
    players: list[User],
    bots: dict[str, RacetimeBot],
) -> Tournament:
    """Seed one tenant's racetime.gg-managed tournament and every online fixture
    hanging off it. Must run inside that tenant's ``tenant_scope``.

    Returns the tournament it created so the caller can report/extend it.
    """
    preset = await _seed_presets(tenant)
    tournament = await _seed_online_tournament(
        tenant, staff, players, preset, bots["alttpr"],
    )
    scheduled, in_progress, finished = await _seed_online_matches(
        tenant, tournament, players,
    )
    await _seed_rooms(tenant, bots["alttpr"], scheduled, in_progress, finished)
    await _seed_speedgaming(tenant, tournament, scheduled)
    await _seed_discord_events(tenant, tournament, scheduled)
    await _seed_qualifiers(tenant, preset)
    print(f"    [{tenant.slug}] online tournament ok")
    return tournament


async def _seed_presets(tenant: Tenant) -> Preset:
    """Seed-rolling presets (PR 1) plus placeholder randomizer credentials.

    Returns the ALTTPR preset, which the online tournament and the qualifier's
    standard pool both point at."""
    preset, _ = await Preset.get_or_create(
        name="ALTTPR Open", tenant=tenant,
        defaults={
            "randomizer": "alttpr",
            "settings": {"glitches": "none", "goal": "ganon", "mode": "open"},
            "description": "Standard open-mode ALTTPR settings.",
        },
    )
    # A DK64 Randomizer preset in the canonical settings-string shape (the site's
    # own portable preset format). The value is a placeholder — dev rolls go
    # through MOCK_SEEDGEN and never send it upstream; swap in a real string from
    # dk64randomizer.com before rolling for real.
    await Preset.get_or_create(
        name="DK64 Community", tenant=tenant,
        defaults={
            "randomizer": "dk64r",
            "settings": {"settings_string": "REPLACE_WITH_WIZZROBE_DK64_SETTINGS_STRING"},
            "description": "DK64 Randomizer settings (settings-string form).",
        },
    )
    # Placeholder randomizer credentials so the keyed backends stay *selectable*
    # in the Presets tab and tournament dialog, and the Randomizer Keys tab is not
    # empty in dev. The default tenant gets all three; the second tenant only the
    # OoT key, so dev demonstrates the per-tenant filter narrowing a selector (and
    # its dk64r preset staying editable without one). Dev rolls go through
    # MOCK_SEEDGEN, so these are never sent upstream.
    wanted = all_specs() if tenant.slug == 'default' else credentials_for('ootr')
    for spec in wanted:
        await RandomizerCredential.get_or_create(
            tenant=tenant, randomizer=spec.randomizer, key=spec.key,
            defaults={"value": f"placeholder-dev-{spec.randomizer}-{spec.key}"},
        )
    return preset


async def _seed_online_tournament(
    tenant: Tenant,
    staff: User,
    players: list[User],
    preset: Preset,
    bot: RacetimeBot,
) -> Tournament:
    """The racetime.gg-managed fixture tournament (PR 3) — the only seeded
    tournament with a ``racetime_bot``."""
    # Authorize the tenant to use the bot so live-race room opening (PR 10),
    # which resolves an authorized bot, has one to pick.
    await RacetimeBotTenant.get_or_create(
        bot=bot, tenant=tenant, defaults={"is_active": True},
    )
    tournament, _ = await Tournament.get_or_create(
        name=ONLINE_TOURNAMENT_NAME, tenant=tenant,
        defaults={
            "description": "Online fixture — races run in racetime.gg rooms.",
            "is_active": True,
            "players_per_match": 2,
            "staff_administered": False,
        },
    )
    await tournament.admins.add(staff)
    for p in players:
        await TournamentPlayers.get_or_create(
            tournament=tournament, user=p, tenant=tenant,
        )
    if tournament.preset_id is None:
        tournament.preset = preset
    tournament.racetime_bot = bot
    tournament.racetime_auto_create_rooms = True
    tournament.room_open_minutes_before = 15
    tournament.racetime_default_goal = "Beat the game"
    await tournament.save()
    return tournament


async def _seed_online_matches(
    tenant: Tenant, tournament: Tournament, players: list[User],
) -> tuple[Match, Match, Match]:
    """One match per online lifecycle state, with its own roster.

    Never stamps ``seated_at``: an online race is not checked in at a station —
    the race room drives the lifecycle, which is exactly why these matches live
    apart from the on-site ones.
    """
    now = now_eastern()

    async def make_match(
        title: str,
        offset_hours: float,
        p1: User,
        p2: User,
        *,
        started: bool = False,
        finished: bool = False,
    ) -> Match:
        scheduled_at = now + timedelta(hours=offset_hours)
        match, created = await Match.get_or_create(
            title=title, tournament=tournament, tenant=tenant,
            defaults={"scheduled_at": scheduled_at, "is_stream_candidate": True},
        )
        if not created:
            return match
        if started or finished:
            match.started_at = scheduled_at
        if finished:
            match.finished_at = scheduled_at + timedelta(hours=1, minutes=36)
            match.confirmed_at = match.finished_at + timedelta(minutes=5)
        await match.save()
        for rank, player in enumerate([p1, p2], 1):
            await MatchPlayers.get_or_create(
                match=match, user=player, tenant=tenant,
                defaults={"finish_rank": rank if finished else None},
            )
        return match

    scheduled = await make_match("Online Scheduled Race", 2, players[0], players[1])
    in_progress = await make_match(
        "Online Race In Progress", -1, players[2], players[3], started=True,
    )
    finished = await make_match(
        "Online Race Finished", -3, players[0], players[2], started=True, finished=True,
    )
    return scheduled, in_progress, finished


async def _seed_rooms(
    tenant: Tenant,
    bot: RacetimeBot,
    scheduled: Match,
    in_progress: Match,
    finished: Match,
) -> None:
    """A reusable room profile plus one race room per room state (PR 4/6), and
    finish times on the finished race's players.

    Keyed on the globally-unique slug with ``update_or_create``: the open room's
    slug predates the tournament split, when it hung off the general-purpose
    tournament's match, so a dev database seeded before the split is re-pointed
    at the online match rather than left dangling on an on-site one.
    """
    await RaceRoomProfile.get_or_create(
        name="Bracket Match", tenant=tenant,
        defaults={
            "goal": "Beat the game",
            "invitational": True,
            "unlisted": False,
            "auto_start": True,
            "allow_comments": True,
            "allow_midrace_chat": True,
            "allow_non_entrant_chat": False,
            "chat_message_delay": 0,
            "start_delay": 15,
            "time_limit": 24,
            "streaming_required": True,
        },
    )

    room_specs = [
        ("dev-room", "Scheduled Race — Bracket", RaceRoomStatus.OPEN, scheduled),
        ("dev-room-live", "Race In Progress — Bracket", RaceRoomStatus.IN_PROGRESS, in_progress),
        ("dev-room-done", "Finished Race — Bracket", RaceRoomStatus.FINISHED, finished),
    ]
    for suffix, room_name, status, match in room_specs:
        await RacetimeRoom.update_or_create(
            slug=f"alttpr/{suffix}-{tenant.slug}",
            defaults={
                "tenant": tenant,
                "bot": bot,
                "category": "alttpr",
                "room_name": room_name,
                "status": status,
                "match": match,
                "opened_at": (
                    match.scheduled_at - timedelta(minutes=15)
                    if match.scheduled_at else None
                ),
            },
        )

    for mp, secs in zip(
        await MatchPlayers.filter(match=finished).order_by("finish_rank"),
        (5400, 5760),
    ):
        if mp.finish_time is None:
            mp.finish_time = secs
            await mp.save()


async def _seed_qualifiers(tenant: Tenant, preset: Preset) -> None:
    """Async Qualifier fixtures (PR 9): an active, open qualifier with two pools,
    a preset-tied pool, permalinks, and runs across states — one finished+approved
    (scored, sets par) and one finished+pending (shows in the reviewer queue) — so
    the admin Qualifiers tab, reviewer queue, and leaderboard all have data, and
    the active-window lockdown is demonstrable (non-staff can't see the board)."""
    now = datetime.now(timezone.utc)
    staff = await User.get_or_none(username="staff_user")
    runner_a = await User.get_or_none(username="player_three")
    runner_b = await User.get_or_none(username="player_four")

    qualifier, _ = await AsyncQualifier.get_or_create(
        name="Dev Async Qualifier", tenant=tenant,
        defaults={
            "description": "Self-paced qualifier fixture for local dev.",
            "event_name": "Wizzrobe Dev Season",
            "opens_at": now - timedelta(days=1),
            "closes_at": now + timedelta(days=7),
            "runs_per_pool": 2,
            "allowed_reattempts": 1,
            "is_active": True,
            "config": {"par_sample_size": 3},
        },
    )
    if staff is not None:
        await qualifier.admins.add(staff)

    standard, _ = await AsyncQualifierPool.get_or_create(
        qualifier=qualifier, name="Standard Pool", tenant=tenant,
        defaults={"preset": preset},
    )
    bonus, _ = await AsyncQualifierPool.get_or_create(
        qualifier=qualifier, name="Bonus Pool", tenant=tenant,
    )

    async def _permalink(pool: AsyncQualifierPool, url: str) -> AsyncQualifierPermalink:
        pl, _ = await AsyncQualifierPermalink.get_or_create(
            pool=pool, url=url, tenant=tenant,
        )
        return pl

    p1 = await _permalink(standard, f"https://alttpr.com/en/h/dev-{tenant.slug}-std-1")
    await _permalink(standard, f"https://alttpr.com/en/h/dev-{tenant.slug}-std-2")
    await _permalink(standard, f"https://alttpr.com/en/h/dev-{tenant.slug}-std-3")
    await _permalink(bonus, f"https://alttpr.com/en/h/dev-{tenant.slug}-bonus-1")
    await _permalink(bonus, f"https://alttpr.com/en/h/dev-{tenant.slug}-bonus-2")

    # A finished, approved, scored run on p1 — par is the run's own time, so its
    # score is 100 and the leaderboard has an entry.
    if runner_a is not None:
        run_a = await AsyncQualifierRun.filter(
            qualifier=qualifier, user=runner_a, permalink=p1
        ).first()
        if run_a is None:
            await AsyncQualifierRun.create(
                tenant=tenant, qualifier=qualifier, user=runner_a, permalink=p1,
                status=AsyncQualifierRunStatus.FINISHED,
                review_status=AsyncQualifierReviewStatus.APPROVED,
                started_at=now - timedelta(hours=3), finished_at=now - timedelta(hours=1, minutes=30),
                elapsed_seconds=5400, runner_vod_url="https://twitch.tv/videos/dev-a",
                reviewed_by=staff, reviewed_at=now - timedelta(hours=1), score=100.0,
            )
            if p1.par_time is None:
                p1.par_time = 5400
                p1.par_updated_at = now
                await p1.save()

    # A finished run awaiting review — populates the reviewer queue.
    if runner_b is not None:
        run_b = await AsyncQualifierRun.filter(
            qualifier=qualifier, user=runner_b, permalink=p1
        ).first()
        if run_b is None:
            run_b = await AsyncQualifierRun.create(
                tenant=tenant, qualifier=qualifier, user=runner_b, permalink=p1,
                status=AsyncQualifierRunStatus.FINISHED,
                review_status=AsyncQualifierReviewStatus.PENDING,
                started_at=now - timedelta(hours=2), finished_at=now - timedelta(minutes=20),
                elapsed_seconds=6000, runner_vod_url="https://twitch.tv/videos/dev-b",
            )
        # A reviewer note on the pending run so the review surface renders notes.
        if staff is not None and not await AsyncQualifierReviewNote.filter(
            run=run_b, tenant=tenant
        ).exists():
            await AsyncQualifierReviewNote.create(
                tenant=tenant, run=run_b, author=staff,
                note="VOD checked through the halfway split; finish looks clean.",
            )

    # A live-race pool (PR 10): a live-flagged permalink + a scheduled live race,
    # so the admin Live Races sub-tab has data to open a room for.
    live_pool, _ = await AsyncQualifierPool.get_or_create(
        qualifier=qualifier, name="Live Race Pool", tenant=tenant,
    )
    live_pl, _ = await AsyncQualifierPermalink.get_or_create(
        pool=live_pool, url=f"https://alttpr.com/en/h/dev-{tenant.slug}-live-1", tenant=tenant,
        defaults={"live_race": True},
    )
    live_race = await AsyncQualifierLiveRace.filter(
        pool=live_pool, match_title="Dev Live Qualifier Race"
    ).first()
    if live_race is None:
        await AsyncQualifierLiveRace.create(
            tenant=tenant, pool=live_pool, permalink=live_pl,
            match_title="Dev Live Qualifier Race",
            status=AsyncQualifierLiveRaceStatus.SCHEDULED,
        )


async def _seed_speedgaming(
    tenant: Tenant, tournament: Tournament, scheduled_match: Match,
) -> None:
    """SpeedGaming ETL fixtures (PR 7): an event link, a synced episode, and a
    sourced match with a mixed real+placeholder roster so the admin SpeedGaming
    tab shows sync health and the schedule shows a match with the read-only
    'Synced from SpeedGaming' badge. Placeholder ``speedgaming_id`` is namespaced
    per tenant (it is globally unique).

    The link is keyed on ``(tenant, event_slug)`` with ``update_or_create``, and
    an already-materialized sourced match is re-pointed, so a dev database seeded
    before the online tournament existed moves its SG fixtures across instead of
    leaving them on the on-site tournament.
    """
    now = datetime.now(timezone.utc)

    link, _ = await SpeedGamingEventLink.update_or_create(
        event_slug=f"wiz-{tenant.slug}", tenant=tenant,
        defaults={
            "tournament": tournament,
            "content_type": None,
            "active": True,
            "sync_interval_minutes": 15,
            "lookahead_hours": 72,
            "last_synced_at": now,
            "last_status": "ok",
        },
    )

    episode, _ = await SpeedGamingEpisode.get_or_create(
        sg_episode_id=f"dev-{tenant.slug}-1", tenant=tenant,
        defaults={
            "event_link": link,
            "title": "Synced Bracket — Round 1",
            "scheduled_at": now + timedelta(days=1),
            "payload": {"id": f"dev-{tenant.slug}-1", "title": "Synced Bracket — Round 1"},
            "content_hash": "devseedhash",
            "sync_status": SyncStatus.SYNCED,
            "synced_at": now,
        },
    )

    sourced_match = await Match.filter(speedgaming_episode=episode).first()
    if sourced_match is None:
        sourced_match = await Match.create(
            tenant=tenant, tournament=tournament,
            scheduled_at=now + timedelta(days=1),
            title="Synced Bracket — Round 1",
            speedgaming_episode=episode,
        )
    elif sourced_match.tournament_id != tournament.id:
        sourced_match.tournament = tournament
        await sourced_match.save()

    placeholder, _ = await User.get_or_create(
        speedgaming_id=f"sg_dev_{tenant.slug}",
        defaults={
            "username": f"sg_dev_{tenant.slug}",
            "display_name": "Unmatched SG Player",
            "is_placeholder": True,
            "is_active": False,
            "dm_notifications": False,
        },
    )

    # A real player alongside the placeholder (from the scheduled match's roster).
    real_player = await MatchPlayers.filter(match=scheduled_match).prefetch_related("user").first()
    roster = [placeholder]
    if real_player is not None:
        roster.append(real_player.user)
    for user in roster:
        # Membership first, then enrol, then add to the match — the order the
        # real ETL uses. Without the membership the placeholder is a person on
        # this community's schedule who does not belong to it, which the
        # membership-coverage audit reports as a gap.
        await TenantMembership.get_or_create(user=user, tenant=tenant)
        await TournamentPlayers.get_or_create(tournament=tournament, user=user, tenant=tenant)
        await MatchPlayers.get_or_create(match=sourced_match, user=user, tenant=tenant)


async def _seed_discord_events(
    tenant: Tenant, tournament: Tournament, scheduled_match: Match,
) -> None:
    """Discord Events mirror fixtures (PR 8): opt the tournament into the mirror
    and seed one already-mirrored :class:`DiscordScheduledEvent` for the scheduled
    match, so the admin Discord Events tab shows an opted-in tournament and a
    non-empty mirrored-events table. ``discord_event_id`` is namespaced per tenant
    (it is globally unique). Requires the tenant to have a linked guild (seed_dev
    sets one).

    Keyed on that globally-unique ``discord_event_id`` rather than the source
    match: a dev database seeded before the tournament split already holds this
    id against the on-site tournament's match, and re-using it under a new
    ``source_id`` would collide.
    """
    if not tournament.discord_events_enabled:
        tournament.discord_events_enabled = True
        tournament.discord_event_duration_minutes = 90
        await tournament.save()

    guild_id = tenant.discord_guild_id
    if guild_id is None:
        return

    # A stable synthetic Discord event id per tenant (well outside real snowflakes).
    discord_event_id = 3900000000000000000 + tenant.id
    await DiscordScheduledEvent.update_or_create(
        discord_event_id=discord_event_id,
        defaults={
            "tenant": tenant,
            "guild_id": guild_id,
            "source_type": DiscordEventSource.MATCH,
            "source_id": scheduled_match.id,
            "title": scheduled_match.title or "Online Scheduled Race",
            "scheduled_at": scheduled_match.scheduled_at,
            "content_hash": "devseedhash",
            "synced_at": datetime.now(timezone.utc),
        },
    )
