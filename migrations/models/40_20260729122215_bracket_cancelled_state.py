from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "bracket"."state" IS 'DRAFT: draft
ACTIVE: active
COMPLETE: complete
CANCELLED: cancelled';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "bracket"."state" IS 'DRAFT: draft
ACTIVE: active
COMPLETE: complete';"""
