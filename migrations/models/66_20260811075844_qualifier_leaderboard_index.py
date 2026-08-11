from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE INDEX IF NOT EXISTS "idx_asyncqualif_qualifi_415dda" ON "asyncqualifierrun" ("qualifier_id", "reattempted", "status", "review_status");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_asyncqualif_qualifi_415dda";"""
