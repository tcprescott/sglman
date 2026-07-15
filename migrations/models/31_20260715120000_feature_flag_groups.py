"""Feature-flag groups (live tiers) + tri-state per-tenant overrides.

Builds the group layer on top of migration 30's per-tenant flags:

1. ``featureflaggroup`` — a super-admin-defined bundle of flags (a live tier). A
   tenant is assigned to at most one via ``tenant.feature_group_id``; ungrouped
   tenants fall back to the single ``is_default`` group.
2. ``tenant.feature_group_id`` — nullable FK, ``ON DELETE SET NULL`` so deleting a
   group reassigns its tenants to ungrouped (→ default fallback), never orphaning.
3. ``tenantfeatureflag.available`` / ``enabled`` become **nullable** (tri-state):
   NULL = inherit (from the group, or the default-on-when-available rule);
   True/False = an explicit override. Existing rows keep their True/False values,
   so they stay as overrides — nothing a live tenant sees changes.

Seeds an **empty** default group (configured later via /platform) and a ready-made
"Online Tournaments" group. Existing per-tenant pins are deliberately left in
place, so gating those features on for current tenants is preserved.

Hand-written (like migrations 14/18-30) to keep the numbered chain contiguous;
every statement is idempotent.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "featureflaggroup" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "name" VARCHAR(100) NOT NULL UNIQUE,
            "description" TEXT,
            "flags" JSONB NOT NULL DEFAULT '[]',
            "is_default" BOOL NOT NULL DEFAULT False,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE "tenant" ADD COLUMN IF NOT EXISTS "feature_group_id" INT
            REFERENCES "featureflaggroup" ("id") ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS "idx_tenant_feature_group_id" ON "tenant" ("feature_group_id");
        ALTER TABLE "tenantfeatureflag" ALTER COLUMN "available" DROP DEFAULT;
        ALTER TABLE "tenantfeatureflag" ALTER COLUMN "available" DROP NOT NULL;
        ALTER TABLE "tenantfeatureflag" ALTER COLUMN "enabled" DROP DEFAULT;
        ALTER TABLE "tenantfeatureflag" ALTER COLUMN "enabled" DROP NOT NULL;
        INSERT INTO "featureflaggroup" ("name", "description", "flags", "is_default")
            VALUES (
                'Default',
                'Live fallback for tenants with no group assigned. Starts empty — edit its flags on /platform.',
                '[]'::jsonb, True
            )
            ON CONFLICT ("name") DO NOTHING;
        INSERT INTO "featureflaggroup" ("name", "description", "flags", "is_default")
            VALUES (
                'Online Tournaments',
                'Async qualifiers, racetime rooms, and SpeedGaming schedule sync.',
                '["async_qualifiers", "racetime_rooms", "speedgaming_etl"]'::jsonb, False
            )
            ON CONFLICT ("name") DO NOTHING;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tenant" DROP COLUMN IF EXISTS "feature_group_id";
        DROP TABLE IF EXISTS "featureflaggroup";
        UPDATE "tenantfeatureflag" SET "available" = False WHERE "available" IS NULL;
        UPDATE "tenantfeatureflag" SET "enabled" = False WHERE "enabled" IS NULL;
        ALTER TABLE "tenantfeatureflag" ALTER COLUMN "available" SET DEFAULT False;
        ALTER TABLE "tenantfeatureflag" ALTER COLUMN "available" SET NOT NULL;
        ALTER TABLE "tenantfeatureflag" ALTER COLUMN "enabled" SET DEFAULT False;
        ALTER TABLE "tenantfeatureflag" ALTER COLUMN "enabled" SET NOT NULL;"""
