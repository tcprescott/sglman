"""Discord Events sync (PR 8): scheduled-event mirror table + per-tournament opt-in.

Additive, idempotent. Two groups of change:

1. ``tournament`` — per-tournament opt-in for the Discord Scheduled Events mirror
   (``discord_events_enabled``), the external event duration, and nullable
   title/description templates.
2. ``discordscheduledevent`` — tenant-scoped reconciliation link between an
   SGLMan schedule row (``source_type`` / ``source_id``) and a Discord Scheduled
   Event (``discord_event_id``, globally unique). ``(tenant, source_type,
   source_id)`` is unique for idempotency.

Hand-written (like migrations 14/18-26) to keep the numbered chain contiguous;
every statement is idempotent.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "discord_events_enabled" BOOL NOT NULL DEFAULT False;
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "discord_event_duration_minutes" INT NOT NULL DEFAULT 60;
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "discord_event_title_template" VARCHAR(255);
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "discord_event_description_template" TEXT;
        CREATE TABLE IF NOT EXISTS "discordscheduledevent" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "guild_id" BIGINT NOT NULL,
            "discord_event_id" BIGINT NOT NULL UNIQUE,
            "source_type" VARCHAR(20) NOT NULL,
            "source_id" INT NOT NULL,
            "title" VARCHAR(255) NOT NULL,
            "scheduled_at" TIMESTAMPTZ,
            "content_hash" VARCHAR(64),
            "synced_at" TIMESTAMPTZ,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            CONSTRAINT "uid_discordevent_tenant_src" UNIQUE ("tenant_id", "source_type", "source_id")
        );
        CREATE INDEX IF NOT EXISTS "idx_discordevent_tenant_id" ON "discordscheduledevent" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_discordevent_guild_id" ON "discordscheduledevent" ("guild_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "discordscheduledevent";
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "discord_event_description_template";
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "discord_event_title_template";
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "discord_event_duration_minutes";
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "discord_events_enabled";"""
