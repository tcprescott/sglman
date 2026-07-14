"""Async Qualifiers core (PR 9): the AsyncQualifier* peer aggregate.

Additive, idempotent. Creates five tenant-scoped tables plus the per-qualifier
``AsyncQualifierAdmins`` M2M join (mirrors ``TournamentAdmins``):

* ``asyncqualifier`` — the qualifier: typed window columns (``opens_at`` /
  ``closes_at``), ``runs_per_pool`` / ``allowed_reattempts``, a validated-JSON
  ``config`` blob, ``is_active``.
* ``asyncqualifierpool`` — a named permalink pool, optional ``preset`` FK
  (SET_NULL); unique ``(qualifier, name)``.
* ``asyncqualifierpermalink`` — one seed URL in a pool with a maintained
  ``par_time`` and a ``live_race`` flag.
* ``asyncqualifierrun`` — a player's attempt: run/review status enums, timing,
  VoD, ``reattempted`` + ``reattempt_reason``, ``score``, reviewer attribution
  and claim-lock.
* ``asyncqualifierreviewnote`` — reviewer notes on a run.

Hand-written (like migrations 14/18-27) to keep the numbered chain contiguous;
every statement is idempotent.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "asyncqualifier" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "name" VARCHAR(255) NOT NULL,
            "description" TEXT,
            "event_name" VARCHAR(255),
            "opens_at" TIMESTAMPTZ,
            "closes_at" TIMESTAMPTZ,
            "runs_per_pool" INT NOT NULL DEFAULT 1,
            "allowed_reattempts" INT NOT NULL DEFAULT 0,
            "config" JSONB,
            "is_active" BOOL NOT NULL DEFAULT True,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS "idx_asyncqual_tenant_id" ON "asyncqualifier" ("tenant_id");
        CREATE TABLE IF NOT EXISTS "AsyncQualifierAdmins" (
            "asyncqualifier_id" INT NOT NULL REFERENCES "asyncqualifier" ("id") ON DELETE CASCADE,
            "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uidx_asyncqualadmins_qual_user"
            ON "AsyncQualifierAdmins" ("asyncqualifier_id", "user_id");
        CREATE TABLE IF NOT EXISTS "asyncqualifierpool" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "name" VARCHAR(255) NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            "qualifier_id" INT NOT NULL REFERENCES "asyncqualifier" ("id") ON DELETE CASCADE,
            "preset_id" INT REFERENCES "preset" ("id") ON DELETE SET NULL,
            CONSTRAINT "uid_asyncpool_qual_name" UNIQUE ("qualifier_id", "name")
        );
        CREATE INDEX IF NOT EXISTS "idx_asyncpool_tenant_id" ON "asyncqualifierpool" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_asyncpool_qualifier_id" ON "asyncqualifierpool" ("qualifier_id");
        CREATE TABLE IF NOT EXISTS "asyncqualifierpermalink" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "url" VARCHAR(1024) NOT NULL,
            "notes" TEXT,
            "live_race" BOOL NOT NULL DEFAULT False,
            "par_time" INT,
            "par_updated_at" TIMESTAMPTZ,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            "pool_id" INT NOT NULL REFERENCES "asyncqualifierpool" ("id") ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS "idx_asyncperm_tenant_id" ON "asyncqualifierpermalink" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_asyncperm_pool_id" ON "asyncqualifierpermalink" ("pool_id");
        CREATE TABLE IF NOT EXISTS "asyncqualifierrun" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "status" VARCHAR(20) NOT NULL DEFAULT 'in_progress',
            "review_status" VARCHAR(20) NOT NULL DEFAULT 'pending',
            "started_at" TIMESTAMPTZ,
            "finished_at" TIMESTAMPTZ,
            "elapsed_seconds" INT,
            "runner_vod_url" VARCHAR(1024),
            "reattempted" BOOL NOT NULL DEFAULT False,
            "reattempt_reason" TEXT,
            "score" DOUBLE PRECISION,
            "reviewed_at" TIMESTAMPTZ,
            "review_claimed_at" TIMESTAMPTZ,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            "qualifier_id" INT NOT NULL REFERENCES "asyncqualifier" ("id") ON DELETE CASCADE,
            "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
            "permalink_id" INT REFERENCES "asyncqualifierpermalink" ("id") ON DELETE SET NULL,
            "reviewed_by_id" INT REFERENCES "user" ("id") ON DELETE SET NULL,
            "review_claimed_by_id" INT REFERENCES "user" ("id") ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS "idx_asyncrun_tenant_id" ON "asyncqualifierrun" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_asyncrun_qual_review" ON "asyncqualifierrun" ("qualifier_id", "review_status");
        CREATE INDEX IF NOT EXISTS "idx_asyncrun_user_id" ON "asyncqualifierrun" ("user_id");
        CREATE INDEX IF NOT EXISTS "idx_asyncrun_permalink_id" ON "asyncqualifierrun" ("permalink_id");
        CREATE TABLE IF NOT EXISTS "asyncqualifierreviewnote" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "note" TEXT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            "run_id" INT NOT NULL REFERENCES "asyncqualifierrun" ("id") ON DELETE CASCADE,
            "author_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS "idx_asyncnote_tenant_id" ON "asyncqualifierreviewnote" ("tenant_id");
        CREATE INDEX IF NOT EXISTS "idx_asyncnote_run_id" ON "asyncqualifierreviewnote" ("run_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "asyncqualifierreviewnote";
        DROP TABLE IF EXISTS "asyncqualifierrun";
        DROP TABLE IF EXISTS "asyncqualifierpermalink";
        DROP TABLE IF EXISTS "asyncqualifierpool";
        DROP TABLE IF EXISTS "AsyncQualifierAdmins";
        DROP TABLE IF EXISTS "asyncqualifier";"""
