from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "challongeapiusage" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "period" VARCHAR(7) NOT NULL UNIQUE,
    "request_count" INT NOT NULL DEFAULT 0,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE "challongeapiusage" IS 'Per-calendar-month tally of real outbound Challonge API requests.';
        ALTER TABLE "tournament" ADD "challonge_last_synced_at" TIMESTAMPTZ;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" DROP COLUMN "challonge_last_synced_at";
        DROP TABLE IF EXISTS "challongeapiusage";"""
