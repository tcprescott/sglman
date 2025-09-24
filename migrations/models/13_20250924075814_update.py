from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `tournament` ADD `rules_url` VARCHAR(255);
        ALTER TABLE `tournament` ADD `max_match_duration` INT;
        ALTER TABLE `tournament` ADD `bracket_url` VARCHAR(255);
        ALTER TABLE `tournament` ADD `average_match_duration` INT;
        ALTER TABLE `tournament` ADD `tournament_format` VARCHAR(255);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `tournament` DROP COLUMN `rules_url`;
        ALTER TABLE `tournament` DROP COLUMN `max_match_duration`;
        ALTER TABLE `tournament` DROP COLUMN `bracket_url`;
        ALTER TABLE `tournament` DROP COLUMN `average_match_duration`;
        ALTER TABLE `tournament` DROP COLUMN `tournament_format`;"""
