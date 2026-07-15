"""Per-tenant feature flags (two-tier: super-admin availability + tenant enable).

Adds ``tenantfeatureflag`` and backfills the flags for features that were
already in live use — Challonge, Equipment, Volunteers, Triforce texts — as
available+enabled for every existing tenant, so gating those subsystems does not
make them vanish for current communities. New/unreleased features (async
qualifiers, racetime rooms, SpeedGaming ETL) ship dark: no row → off.

The backfill flag keys mirror ``application.feature_flags.established_flags()``
(the ``established=True`` specs). Keep the two in sync when gating another
already-live feature.

Hand-written (like migrations 14/18-29) to keep the numbered chain contiguous;
every statement is idempotent.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "tenantfeatureflag" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "flag" VARCHAR(64) NOT NULL,
            "available" BOOL NOT NULL DEFAULT False,
            "enabled" BOOL NOT NULL DEFAULT False,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            CONSTRAINT "uid_tenantfeatureflag_tenant_flag" UNIQUE ("tenant_id", "flag")
        );
        CREATE INDEX IF NOT EXISTS "idx_tenantfeatureflag_tenant_id" ON "tenantfeatureflag" ("tenant_id");
        INSERT INTO "tenantfeatureflag" ("tenant_id", "flag", "available", "enabled")
            SELECT "tenant"."id", f."flag", True, True
            FROM "tenant"
            CROSS JOIN (VALUES ('challonge'), ('equipment'), ('volunteers'), ('triforce_texts')) AS f("flag")
            ON CONFLICT ("tenant_id", "flag") DO NOTHING;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "tenantfeatureflag";"""
