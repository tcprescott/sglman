"""Dev-seed fixtures for the online-tournament features (PRs 1-6).

Split out of ``seed_dev.py`` to keep that file under the length guideline. These
functions are called from ``seed_dev.py`` — they assume an open Tortoise
connection and (for the per-tenant helper) an active ``tenant_scope``.

What they cover:

- **Presets** (PR 1) — a per-tenant ``Preset`` assigned to the dev tournament.
- **Racetime identity** (PR 2) — two players linked to racetime handles.
- **Racetime bots** (PR 3/4) — platform-level (no tenant FK), one connected and
  one parked in an error state so the ``/platform`` health table shows both.
- **Racetime config + rooms** (PR 3/4/6) — the tournament's bot + auto-open
  config, a room profile, an open room on the scheduled match, and finish times
  on the finished match's players.
"""
from datetime import datetime, timedelta, timezone

from models import (
    User, UserRole, Role, Tenant, Tournament, Match, MatchPlayers, TournamentPlayers,
    Preset, RacetimeBot, RacetimeBotTenant, RacetimeRoom, RaceRoomProfile,
    SpeedGamingEventLink, SpeedGamingEpisode, SyncStatus,
    DiscordScheduledEvent, DiscordEventSource,
    BotStatus, RaceRoomStatus,
    AsyncQualifier, AsyncQualifierPool, AsyncQualifierPermalink, AsyncQualifierRun,
    AsyncQualifierRunStatus, AsyncQualifierReviewStatus, AsyncQualifierReviewNote,
    AsyncQualifierLiveRace, AsyncQualifierLiveRaceStatus,
)
from application.utils.timezone import now_eastern


async def link_racetime_identities(users: dict[str, User]) -> None:
    """Link two players to racetime handles (PR 2) and grant a global
    SUPER_ADMIN so the ``/platform`` surface is reachable in dev."""
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

    await UserRole.get_or_create(
        user=users["staff_user"], role=Role.SUPER_ADMIN, tenant=None,
        defaults={"granted_by": None},
    )


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
    tournament: Tournament,
    scheduled_match: Match,
    finished_match: Match,
    bots: dict[str, RacetimeBot],
) -> None:
    """Seed preset (PR 1), racetime config (PR 3), and a room profile + open
    room + finish times (PR 4/6) for one tenant. Must run inside that tenant's
    ``tenant_scope``."""
    now = now_eastern()
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
    # dk64randomizer.com before enabling the DK64_RANDOMIZER flag in production.
    await Preset.get_or_create(
        name="DK64 Community", tenant=tenant,
        defaults={
            "randomizer": "dk64r",
            "settings": {"settings_string": "REPLACE_WITH_WIZZROBE_DK64_SETTINGS_STRING"},
            "description": "DK64 Randomizer settings (settings-string form).",
        },
    )
    alttpr_bot = bots["alttpr"]
    # Authorize the tenant to use the bot so live-race room opening (PR 10),
    # which resolves an authorized bot, has one to pick.
    await RacetimeBotTenant.get_or_create(
        bot=alttpr_bot, tenant=tenant, defaults={"is_active": True},
    )
    if tournament.preset_id is None:
        tournament.preset = preset
    tournament.racetime_bot = alttpr_bot
    tournament.racetime_auto_create_rooms = True
    tournament.room_open_minutes_before = 15
    tournament.racetime_default_goal = "Beat the game"
    await tournament.save()

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

    await RacetimeRoom.get_or_create(
        slug=f"alttpr/dev-room-{tenant.slug}", tenant=tenant,
        defaults={
            "bot": alttpr_bot,
            "category": "alttpr",
            "room_name": "Scheduled Match — Bracket",
            "status": RaceRoomStatus.OPEN,
            "match": scheduled_match,
            "opened_at": now,
        },
    )
    for mp, secs in zip(
        await MatchPlayers.filter(match=finished_match).order_by("finish_rank"),
        (5400, 5760),
    ):
        if mp.finish_time is None:
            mp.finish_time = secs
            await mp.save()

    await _seed_speedgaming(tenant, tournament, scheduled_match)
    await _seed_discord_events(tenant, tournament, scheduled_match)
    await _seed_qualifiers(tenant, preset)
    print(f"    [{tenant.slug}] online tournaments ok")


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
    per tenant (it is globally unique)."""
    now = datetime.now(timezone.utc)

    link, _ = await SpeedGamingEventLink.get_or_create(
        tournament=tournament, event_slug=f"wiz-{tenant.slug}", tenant=tenant,
        defaults={
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
        # Enroll first (the real ETL does the same), then add to the match, so a
        # sourced match's roster shows both real and placeholder entrants.
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
    sets one)."""
    if not tournament.discord_events_enabled:
        tournament.discord_events_enabled = True
        tournament.discord_event_duration_minutes = 90
        await tournament.save()

    guild_id = tenant.discord_guild_id
    if guild_id is None:
        return

    # A stable synthetic Discord event id per tenant (well outside real snowflakes).
    discord_event_id = 3900000000000000000 + tenant.id
    await DiscordScheduledEvent.get_or_create(
        tenant=tenant,
        source_type=DiscordEventSource.MATCH,
        source_id=scheduled_match.id,
        defaults={
            "guild_id": guild_id,
            "discord_event_id": discord_event_id,
            "title": scheduled_match.title or "Scheduled Match — Bracket",
            "scheduled_at": scheduled_match.scheduled_at,
            "content_hash": "devseedhash",
            "synced_at": datetime.now(timezone.utc),
        },
    )
