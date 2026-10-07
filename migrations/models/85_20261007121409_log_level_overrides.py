from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "logleveloverride" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "logger_name" VARCHAR(255) NOT NULL UNIQUE,
    "level" VARCHAR(16) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_by_id" INT REFERENCES "user" ("id") ON DELETE SET NULL
);
COMMENT ON TABLE "logleveloverride" IS 'A super-admin''s level for one stdlib logger, reapplied at every startup.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "logleveloverride";"""
