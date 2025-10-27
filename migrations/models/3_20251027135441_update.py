from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `matchplayers` ADD `finish_rank` INT;
        ALTER TABLE `matchplayers` ADD `assigned_station` VARCHAR(50);
        ALTER TABLE `matchplayers` DROP COLUMN `confirmed`;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `matchplayers` ADD `confirmed` BOOL NOT NULL DEFAULT 0;
        ALTER TABLE `matchplayers` DROP COLUMN `finish_rank`;
        ALTER TABLE `matchplayers` DROP COLUMN `assigned_station`;"""
