from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "asyncqualifier" ADD "review_backlog_notified_at" TIMESTAMPTZ;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "asyncqualifier" DROP COLUMN "review_backlog_notified_at";"""
