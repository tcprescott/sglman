from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `match` RENAME COLUMN `started_at` TO `seated_at`;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `match` RENAME COLUMN `seated_at` TO `started_at`;"""
