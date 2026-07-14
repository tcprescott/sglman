"""Online-tournament foundations (PR 0): system user, config substrate.

Three additive, idempotent changes shared by every later online-tournament PR:

1. ``tournament.config`` — nullable JSONB holding the schema-validated hybrid
   config (messaging templates, scoring params, strategy choices). Typed knobs
   stay their own columns; this is the JSON half.
2. ``user.is_system`` — marks the single reserved automation actor.
3. Seed that system ``User`` (sentinel ``discord_id`` = 0) so a fresh production
   DB has it immediately; ``UserService.get_system_user`` get-or-creates the same
   row, so the two paths converge.

The new ``Role`` members (``preset_manager`` / ``sync_admin`` / ``qualifier_admin``)
need **no** migration: ``UserRole.role`` is a ``VARCHAR(32)`` (a ``CharEnumField``),
so the enum widening is a code-only change.

Hand-written (like migrations 14/18/19/20) to keep the numbered chain contiguous;
every statement is idempotent.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "config" JSONB;
        ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "is_system" BOOL NOT NULL DEFAULT False;
        INSERT INTO "user" ("discord_id", "username", "is_system", "is_active", "dm_notifications")
        VALUES (0, 'System', True, False, False)
        ON CONFLICT ("discord_id") DO NOTHING;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DELETE FROM "user" WHERE "discord_id" = 0 AND "is_system" = True;
        ALTER TABLE "user" DROP COLUMN IF EXISTS "is_system";
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "config";"""
