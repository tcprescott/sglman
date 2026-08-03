from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" ADD "signups_open_at" TIMESTAMPTZ;
        ALTER TABLE "tournament" ADD "signups_close_at" TIMESTAMPTZ;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" DROP COLUMN "signups_open_at";
        ALTER TABLE "tournament" DROP COLUMN "signups_close_at";"""
