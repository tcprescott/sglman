from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `match` ADD `confirmed_at` DATETIME(6);
        ALTER TABLE `match` ADD `started_at` DATETIME(6);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `match` DROP COLUMN `confirmed_at`;
        ALTER TABLE `match` DROP COLUMN `started_at`;"""
