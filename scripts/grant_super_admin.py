#!/usr/bin/env python3
"""Grant the global SUPER_ADMIN role to a user by Discord ID.

Run from the project root:
    poetry run python scripts/grant_super_admin.py <discord_id>

SUPER_ADMIN is the platform-wide role that manages tenants on ``/platform``. Its
``UserRole`` row carries ``tenant=NULL`` (the only role that may). This is the
post-migration bootstrap: after the additive migration lands, every existing
role is a per-tenant STAFF/etc., so the operator grants themselves SUPER_ADMIN
here. Idempotent — safe to re-run. The user must already exist.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from migrations.tortoise_config import TORTOISE_ORM
from tortoise import Tortoise
from models import Role, User, UserRole


async def grant_super_admin(discord_id: str) -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        user = await User.get_or_none(discord_id=discord_id)
        if user is None:
            print(f"No user found with discord_id {discord_id!r}. "
                  "They must log in at least once before being granted a role.")
            sys.exit(1)

        _, created = await UserRole.get_or_create(
            user=user, role=Role.SUPER_ADMIN, tenant=None, defaults={"granted_by": None},
        )
        label = user.display_name or user.username or discord_id
        if created:
            print(f"Granted SUPER_ADMIN to {label} ({discord_id}).")
        else:
            print(f"{label} ({discord_id}) already has SUPER_ADMIN.")
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: poetry run python scripts/grant_super_admin.py <discord_id>")
        sys.exit(2)
    asyncio.run(grant_super_admin(sys.argv[1]))
