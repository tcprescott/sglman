from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `match` ADD `title` VARCHAR(255);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `match` DROP COLUMN `title`;"""
