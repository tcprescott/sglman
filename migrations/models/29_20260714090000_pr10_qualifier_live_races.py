"""Async Qualifier live races (PR 10): the AsyncQualifierLiveRace table + run FK.

Additive, idempotent. Adds:

* ``asyncqualifierliverace`` — a synchronous racetime race for a pool: FKs to
  ``pool`` (CASCADE) and nullable ``permalink`` / ``episode`` (SET_NULL), a
  ``match_title``, a globally-unique nullable ``racetime_slug`` mirroring the
  room slug, and a ``status`` enum.
* ``asyncqualifierrun.live_race_id`` — the deferred (PR 9) FK linking a captured
  run back to the live race it came from (SET_NULL) + its index.

Hand-written (like migrations 14/18-28) to keep the numbered chain contiguous;
every statement is idempotent.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "asyncqualifierliverace" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "match_title" VARCHAR(255) NOT NULL,
            "racetime_slug" VARCHAR(255) UNIQUE,
            "status" VARCHAR(20) NOT NULL DEFAULT 'scheduled',
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            "pool_id" INT NOT NULL REFERENCES "asyncqualifierpool" ("id") ON DELETE CASCADE,
            "permalink_id" INT REFERENCES "asyncqualifierpermalink" ("id") ON DELETE SET NULL,
            "episode_id" INT REFERENCES "speedgamingepisode" ("id") ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS "idx_asyncliverace_tenant_id" ON "asyncqualifierliverace" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_asyncliverace_pool_id" ON "asyncqualifierliverace" ("pool_id");
        ALTER TABLE "asyncqualifierrun"
            ADD COLUMN IF NOT EXISTS "live_race_id" INT
            REFERENCES "asyncqualifierliverace" ("id") ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS "idx_asyncrun_live_race_id" ON "asyncqualifierrun" ("live_race_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "asyncqualifierrun" DROP COLUMN IF EXISTS "live_race_id";
        DROP TABLE IF EXISTS "asyncqualifierliverace";"""
