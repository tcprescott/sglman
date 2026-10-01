from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "accommodation_request" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "status" VARCHAR(20) NOT NULL DEFAULT 'new',
    "details" TEXT,
    "staff_notes" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_accommodati_tenant__94b2d8" UNIQUE ("tenant_id", "user_id")
);
COMMENT ON COLUMN "accommodation_request"."status" IS 'NEW: new\nACKNOWLEDGED: acknowledged\nARRANGED: arranged\nWITHDRAWN: withdrawn';
COMMENT ON TABLE "accommodation_request" IS 'A member''s request for ADA accommodation in one community.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "accommodation_request";"""
