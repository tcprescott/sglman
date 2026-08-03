from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "provider_task" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "provider" VARCHAR(32) NOT NULL,
    "operation" VARCHAR(32) NOT NULL,
    "status" VARCHAR(16) NOT NULL DEFAULT 'queued',
    "provider_task_id" VARCHAR(128),
    "provider_params" JSONB,
    "settings_snapshot" JSONB,
    "error" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completed_at" TIMESTAMPTZ,
    "match_id" INT REFERENCES "match" ("id") ON DELETE CASCADE,
    "preset_id" INT REFERENCES "preset" ("id") ON DELETE SET NULL,
    "requested_by_id" INT REFERENCES "user" ("id") ON DELETE SET NULL,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_provider_ta_status_41840e" ON "provider_task" ("status", "provider");
COMMENT ON COLUMN "provider_task"."status" IS 'QUEUED: queued\nRUNNING: running\nSUCCEEDED: succeeded\nFAILED: failed\nABANDONED: abandoned';
COMMENT ON TABLE "provider_task" IS 'One long-running call to an upstream provider, tracked across restarts.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "provider_task";"""
