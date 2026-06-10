#!/usr/bin/env python3
"""Grant the STAFF role to a user by Discord ID.

Run from the project root:
    poetry run python scripts/grant_staff.py <discord_id>

Idempotent — safe to re-run. The user must already exist (they are created on
first login). Requires the schema to already exist (run ./start.sh dev or
aerich upgrade first).
"""
import asyncio
import sys
from pathlib import Path

# Ensure project root is on the path when run as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from migrations.tortoise_config import TORTOISE_ORM
from tortoise import Tortoise
from models import User, UserRole, Role


async def grant_staff(discord_id: str) -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        user = await User.get_or_none(discord_id=discord_id)
        if user is None:
            print(f"No user found with discord_id {discord_id!r}. "
                  "They must log in at least once before being granted a role.")
            sys.exit(1)

        _, created = await UserRole.get_or_create(
            user=user, role=Role.STAFF, defaults={"granted_by": None},
        )
        label = user.display_name or user.username or discord_id
        if created:
            print(f"Granted STAFF to {label} ({discord_id}).")
        else:
            print(f"{label} ({discord_id}) already has STAFF.")
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: poetry run python scripts/grant_staff.py <discord_id>")
        sys.exit(2)
    asyncio.run(grant_staff(sys.argv[1]))
