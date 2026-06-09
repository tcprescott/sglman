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
from datetime import timedelta
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
)
from application.utils.timezone import now_eastern


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
        ("100000000000000004", "player_one",   "Player One",   None),
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

    await Tortoise.close_connections()
    print("Seeding complete.")


asyncio.run(seed())
