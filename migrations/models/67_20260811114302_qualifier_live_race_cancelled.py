from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "asyncqualifierliverace"."status" IS 'SCHEDULED: scheduled
PENDING: pending
IN_PROGRESS: in_progress
FINISHED: finished
CANCELLED: cancelled';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "asyncqualifierliverace"."status" IS 'SCHEDULED: scheduled
PENDING: pending
IN_PROGRESS: in_progress
FINISHED: finished';"""
