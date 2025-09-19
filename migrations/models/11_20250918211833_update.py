from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `tournament` ADD `staff_administered` BOOL NOT NULL DEFAULT 0;
        ALTER TABLE `tournament` ADD `description` LONGTEXT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `tournament` DROP COLUMN `staff_administered`;
        ALTER TABLE `tournament` DROP COLUMN `description`;"""
