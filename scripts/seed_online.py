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
from models import (
    User, UserRole, Role, Tenant, Tournament, Match, MatchPlayers,
    Preset, RacetimeBot, RacetimeRoom, RaceRoomProfile,
    BotStatus, RaceRoomStatus,
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
    alttpr_bot = bots["alttpr"]
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
    print(f"    [{tenant.slug}] online tournaments ok")
