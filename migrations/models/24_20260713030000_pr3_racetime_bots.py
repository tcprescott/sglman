"""Racetime bots (PR 3): bot/grant/profile/room tables + ``tournament`` config.

Additive, idempotent. Introduces the data + admin half of the racetime room
automation (no live websocket — that is PR 4):

1. ``racetimebot`` — global (no tenant) bot per game ``category`` (unique),
   holding that category's OAuth ``client_id``/``client_secret`` plus health
   fields written later by the PR 4 runtime.
2. ``racetimebottenant`` — the SUPER_ADMIN authorization grant (many-to-many;
   composite ``unique (bot_id, tenant_id)``).
3. ``raceroomprofile`` — tenant-scoped reusable room settings
   (``unique (tenant_id, name)``).
4. ``racetimeroom`` — its own model with a globally-unique, indexed ``slug`` and
   a OneToOne to ``match`` (both FKs ``ON DELETE SET NULL``).
5. ``tournament`` racetime config columns: ``racetime_bot_id`` +
   ``race_room_profile_id`` (both SET_NULL FKs), ``racetime_auto_create_rooms``,
   ``room_open_minutes_before``, ``require_racetime_link``,
   ``racetime_default_goal``.

Hand-written (like migrations 14/18-23) to keep the numbered chain contiguous;
every statement is idempotent.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "racetimebot" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "category" VARCHAR(64) NOT NULL UNIQUE,
            "client_id" VARCHAR(255) NOT NULL,
            "client_secret" VARCHAR(255) NOT NULL,
            "name" VARCHAR(255) NOT NULL,
            "description" TEXT,
            "is_active" BOOL NOT NULL DEFAULT True,
            "handler_class" VARCHAR(255),
            "status" VARCHAR(20) NOT NULL DEFAULT 'unknown',
            "status_message" TEXT,
            "last_connected_at" TIMESTAMPTZ,
            "last_checked_at" TIMESTAMPTZ,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS "racetimebottenant" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "is_active" BOOL NOT NULL DEFAULT True,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "bot_id" INT NOT NULL REFERENCES "racetimebot" ("id") ON DELETE CASCADE,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            CONSTRAINT "uid_racetimebottenant_bot_tenant" UNIQUE ("bot_id", "tenant_id")
        );
        CREATE INDEX IF NOT EXISTS "idx_racetimebottenant_bot_id" ON "racetimebottenant" ("bot_id");
        CREATE INDEX IF NOT EXISTS "idx_racetimebottenant_tenant_id" ON "racetimebottenant" ("tenant_id");
        CREATE TABLE IF NOT EXISTS "raceroomprofile" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "name" VARCHAR(255) NOT NULL,
            "goal" VARCHAR(255),
            "invitational" BOOL NOT NULL DEFAULT False,
            "unlisted" BOOL NOT NULL DEFAULT False,
            "auto_start" BOOL NOT NULL DEFAULT True,
            "allow_comments" BOOL NOT NULL DEFAULT True,
            "allow_midrace_chat" BOOL NOT NULL DEFAULT True,
            "allow_non_entrant_chat" BOOL NOT NULL DEFAULT True,
            "chat_message_delay" INT NOT NULL DEFAULT 0,
            "start_delay" INT NOT NULL DEFAULT 15,
            "time_limit" INT NOT NULL DEFAULT 24,
            "streaming_required" BOOL NOT NULL DEFAULT False,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            CONSTRAINT "uid_raceroomprofile_tenant_name" UNIQUE ("tenant_id", "name")
        );
        CREATE INDEX IF NOT EXISTS "idx_raceroomprofile_tenant_id" ON "raceroomprofile" ("tenant_id");
        CREATE TABLE IF NOT EXISTS "racetimeroom" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "slug" VARCHAR(255) NOT NULL UNIQUE,
            "category" VARCHAR(64) NOT NULL,
            "room_name" VARCHAR(255),
            "status" VARCHAR(20) NOT NULL DEFAULT 'open',
            "opened_at" TIMESTAMPTZ,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            "bot_id" INT REFERENCES "racetimebot" ("id") ON DELETE SET NULL,
            "match_id" INT UNIQUE REFERENCES "match" ("id") ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS "idx_racetimeroom_slug" ON "racetimeroom" ("slug");
        CREATE INDEX IF NOT EXISTS "idx_racetimeroom_tenant_id" ON "racetimeroom" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_racetimeroom_bot_id" ON "racetimeroom" ("bot_id");
        CREATE INDEX IF NOT EXISTS "idx_racetimeroom_match_id" ON "racetimeroom" ("match_id");
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "racetime_bot_id" INT;
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "race_room_profile_id" INT;
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "racetime_auto_create_rooms" BOOL NOT NULL DEFAULT False;
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "room_open_minutes_before" INT NOT NULL DEFAULT 30;
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "require_racetime_link" BOOL NOT NULL DEFAULT False;
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "racetime_default_goal" VARCHAR(255);
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_tournamen_racetimebot_fk'
            ) THEN
                ALTER TABLE "tournament"
                    ADD CONSTRAINT "fk_tournamen_racetimebot_fk"
                    FOREIGN KEY ("racetime_bot_id") REFERENCES "racetimebot" ("id") ON DELETE SET NULL;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_tournamen_raceroomprofile_fk'
            ) THEN
                ALTER TABLE "tournament"
                    ADD CONSTRAINT "fk_tournamen_raceroomprofile_fk"
                    FOREIGN KEY ("race_room_profile_id") REFERENCES "raceroomprofile" ("id") ON DELETE SET NULL;
            END IF;
        END$$;
        CREATE INDEX IF NOT EXISTS "idx_tournament_racetime_bot_id" ON "tournament" ("racetime_bot_id");
        CREATE INDEX IF NOT EXISTS "idx_tournament_race_room_profile_id" ON "tournament" ("race_room_profile_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" DROP CONSTRAINT IF EXISTS "fk_tournamen_racetimebot_fk";
        ALTER TABLE "tournament" DROP CONSTRAINT IF EXISTS "fk_tournamen_raceroomprofile_fk";
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "racetime_bot_id";
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "race_room_profile_id";
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "racetime_auto_create_rooms";
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "room_open_minutes_before";
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "require_racetime_link";
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "racetime_default_goal";
        DROP TABLE IF EXISTS "racetimeroom";
        DROP TABLE IF EXISTS "raceroomprofile";
        DROP TABLE IF EXISTS "racetimebottenant";
        DROP TABLE IF EXISTS "racetimebot";"""
