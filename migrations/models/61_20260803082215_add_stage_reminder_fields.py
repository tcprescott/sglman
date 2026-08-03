from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "match" ADD "stage_reminder_sent_at" TIMESTAMPTZ;
        ALTER TABLE "tournament" ADD "stage_reminder_minutes" INT NOT NULL DEFAULT 30;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "match" DROP COLUMN "stage_reminder_sent_at";
        ALTER TABLE "tournament" DROP COLUMN "stage_reminder_minutes";"""
