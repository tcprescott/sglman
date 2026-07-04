from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "webpushsubscription" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "endpoint" VARCHAR(1024) NOT NULL UNIQUE,
    "p256dh" VARCHAR(128) NOT NULL,
    "auth" VARCHAR(64) NOT NULL,
    "user_agent" VARCHAR(255),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_used_at" TIMESTAMPTZ,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_webpushsub_user_id_9c2f11" ON "webpushsubscription" ("user_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "webpushsubscription";"""
