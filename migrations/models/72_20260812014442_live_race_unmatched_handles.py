from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "asyncqualifierliverace" ADD "unmatched_handles" JSONB;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "asyncqualifierliverace" DROP COLUMN "unmatched_handles";"""
