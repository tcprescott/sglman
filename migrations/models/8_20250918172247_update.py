from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `match` ADD `finished_at` DATETIME(6);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `match` DROP COLUMN `finished_at`;"""
