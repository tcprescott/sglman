from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "user" ADD "twitch_user_id" VARCHAR(64);
        ALTER TABLE "user" ADD "twitch_username" VARCHAR(255);
        ALTER TABLE "user" ADD "twitch_linked_at" TIMESTAMPTZ;
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_user_twitch_user_id"
            ON "user" ("twitch_user_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uid_user_twitch_user_id";
        ALTER TABLE "user" DROP COLUMN "twitch_user_id";
        ALTER TABLE "user" DROP COLUMN "twitch_username";
        ALTER TABLE "user" DROP COLUMN "twitch_linked_at";"""
