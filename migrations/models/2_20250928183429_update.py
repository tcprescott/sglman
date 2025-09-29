from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `announcement` ADD `important` BOOL NOT NULL DEFAULT 0;
        ALTER TABLE `announcement` ADD `tournament_id` INT;
        ALTER TABLE `announcement` ADD CONSTRAINT `fk_announce_tourname_81bba289` FOREIGN KEY (`tournament_id`) REFERENCES `tournament` (`id`) ON DELETE CASCADE;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `announcement` DROP FOREIGN KEY `fk_announce_tourname_81bba289`;
        ALTER TABLE `announcement` DROP COLUMN `important`;
        ALTER TABLE `announcement` DROP COLUMN `tournament_id`;"""
