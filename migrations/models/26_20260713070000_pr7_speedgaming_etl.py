"""SpeedGaming ETL (PR 7): placeholder users + SG staging tables.

Additive, idempotent. Three groups of change:

1. **Placeholder-user pattern** on the global ``user`` table: ``discord_id``
   becomes nullable (Postgres keeps the existing unique index — many NULLs are
   allowed), plus ``is_placeholder`` and a unique ``speedgaming_id``. A CHECK
   constraint (``discord_id IS NOT NULL OR is_placeholder``) guarantees only a
   placeholder may lack a discord id. The seeded system user (``discord_id`` = 0)
   and every real account satisfy the CHECK unchanged.
2. ``speedgamingeventlink`` — tenant-scoped config (SG event slug ↔ tournament)
   with the observability fields the "observable sync" promise needs.
3. ``speedgamingepisode`` — tenant-scoped staging record, unique
   ``(tenant, sg_episode_id)``; plus ``match.speedgaming_episode_id`` — the
   single canonical source-marker FK (SET_NULL), globally unique (OneToOne).

Hand-written (like migrations 14/18-25) to keep the numbered chain contiguous;
every statement is idempotent.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "user" ALTER COLUMN "discord_id" DROP NOT NULL;
        ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "is_placeholder" BOOL NOT NULL DEFAULT False;
        ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "speedgaming_id" VARCHAR(64);
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_user_speedgaming_id" ON "user" ("speedgaming_id");
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'ck_user_discord_or_placeholder'
            ) THEN
                ALTER TABLE "user"
                    ADD CONSTRAINT "ck_user_discord_or_placeholder"
                    CHECK ("discord_id" IS NOT NULL OR "is_placeholder");
            END IF;
        END$$;
        CREATE TABLE IF NOT EXISTS "speedgamingeventlink" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "event_slug" VARCHAR(128) NOT NULL,
            "content_type" VARCHAR(64),
            "active" BOOL NOT NULL DEFAULT True,
            "sync_interval_minutes" INT NOT NULL DEFAULT 15,
            "lookahead_hours" INT NOT NULL DEFAULT 72,
            "last_synced_at" TIMESTAMPTZ,
            "last_status" VARCHAR(32),
            "last_error" TEXT,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            "tournament_id" INT NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE,
            CONSTRAINT "uid_sgeventlink_tenant_tourn_slug" UNIQUE ("tenant_id", "tournament_id", "event_slug")
        );
        CREATE INDEX IF NOT EXISTS "idx_sgeventlink_tenant_id" ON "speedgamingeventlink" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_sgeventlink_tournament_id" ON "speedgamingeventlink" ("tournament_id");
        CREATE TABLE IF NOT EXISTS "speedgamingepisode" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "sg_episode_id" VARCHAR(64) NOT NULL,
            "title" VARCHAR(255),
            "scheduled_at" TIMESTAMPTZ,
            "payload" JSONB,
            "content_hash" VARCHAR(64),
            "sync_status" VARCHAR(20) NOT NULL DEFAULT 'pending',
            "synced_at" TIMESTAMPTZ,
            "sync_error" TEXT,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            "event_link_id" INT REFERENCES "speedgamingeventlink" ("id") ON DELETE SET NULL,
            CONSTRAINT "uid_sgepisode_tenant_sgid" UNIQUE ("tenant_id", "sg_episode_id")
        );
        CREATE INDEX IF NOT EXISTS "idx_sgepisode_tenant_id" ON "speedgamingepisode" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_sgepisode_event_link_id" ON "speedgamingepisode" ("event_link_id");
        ALTER TABLE "match" ADD COLUMN IF NOT EXISTS "speedgaming_episode_id" INT;
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_match_sgepisode_fk'
            ) THEN
                ALTER TABLE "match"
                    ADD CONSTRAINT "fk_match_sgepisode_fk"
                    FOREIGN KEY ("speedgaming_episode_id") REFERENCES "speedgamingepisode" ("id") ON DELETE SET NULL;
            END IF;
        END$$;
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_match_speedgaming_episode_id" ON "match" ("speedgaming_episode_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "match" DROP CONSTRAINT IF EXISTS "fk_match_sgepisode_fk";
        DROP INDEX IF EXISTS "uid_match_speedgaming_episode_id";
        ALTER TABLE "match" DROP COLUMN IF EXISTS "speedgaming_episode_id";
        DROP TABLE IF EXISTS "speedgamingepisode";
        DROP TABLE IF EXISTS "speedgamingeventlink";
        ALTER TABLE "user" DROP CONSTRAINT IF EXISTS "ck_user_discord_or_placeholder";
        DROP INDEX IF EXISTS "uid_user_speedgaming_id";
        ALTER TABLE "user" DROP COLUMN IF EXISTS "speedgaming_id";
        ALTER TABLE "user" DROP COLUMN IF EXISTS "is_placeholder";"""
