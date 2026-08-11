from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "asyncqualifier" ADD "window_state_notified" VARCHAR(16);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "asyncqualifier" DROP COLUMN "window_state_notified";"""
