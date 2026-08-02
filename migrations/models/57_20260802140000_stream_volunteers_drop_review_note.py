from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "matchstreamvolunteer" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "match_id" INT NOT NULL REFERENCES "match" ("id") ON DELETE CASCADE,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_matchstream_user_id_9c1e2f" UNIQUE ("user_id", "match_id")
);
        CREATE INDEX IF NOT EXISTS "idx_matchstream_match__6b3a41" ON "matchstreamvolunteer" ("match_id");
        ALTER TABLE "match" DROP COLUMN IF EXISTS "review_note";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "match" ADD "review_note" TEXT;
        DROP TABLE IF EXISTS "matchstreamvolunteer";"""
