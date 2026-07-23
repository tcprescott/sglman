"""Per-tournament "tournament days" override.

Additive, idempotent. Adds three nullable columns to ``tournament`` so a single
tournament can override the tenant-wide event window / per-date hours it
otherwise inherits from ``SystemConfiguration`` (see ``SystemConfigService``):

* ``event_start_date`` / ``event_end_date`` — override the event date window.
* ``tournament_hours`` — nullable JSONB of the same shape as the tenant blob,
  ``{"YYYY-MM-DD": {"open": "HH:MM", "close": "HH:MM"}}``.

All nullable → a NULL falls back to the tenant setting at the use-site.

Hand-written (like migrations 14/18-27) to keep the numbered chain contiguous;
every statement is idempotent.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "event_start_date" DATE;
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "event_end_date" DATE;
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "tournament_hours" JSONB;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "tournament_hours";
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "event_end_date";
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "event_start_date";"""
