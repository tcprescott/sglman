from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "webhook" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "url" VARCHAR(1024) NOT NULL,
    "secret" VARCHAR(128) NOT NULL,
    "event_types" JSONB NOT NULL,
    "is_active" BOOL NOT NULL DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
        CREATE TABLE IF NOT EXISTS "webhookdelivery" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "event_type" VARCHAR(100) NOT NULL,
    "payload" TEXT NOT NULL,
    "response_status" INT,
    "attempt_count" INT NOT NULL DEFAULT 0,
    "success" BOOL NOT NULL DEFAULT False,
    "error" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "delivered_at" TIMESTAMPTZ,
    "webhook_id" INT NOT NULL REFERENCES "webhook" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_webhookdeli_created_45160f" ON "webhookdelivery" ("created_at");
CREATE INDEX IF NOT EXISTS "idx_webhookdeli_webhook_db94de" ON "webhookdelivery" ("webhook_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "webhook";
        DROP TABLE IF EXISTS "webhookdelivery";"""
