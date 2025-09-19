from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `tournament` ADD `players_per_match` INT NOT NULL DEFAULT 2;
        ALTER TABLE `tournament` ADD `team_size` INT NOT NULL DEFAULT 1;
        ALTER TABLE `tournament` ADD `is_active` BOOL NOT NULL DEFAULT 1;
        CREATE TABLE `tournamentadmins` (
    `tournament_id` INT NOT NULL REFERENCES `tournament` (`id`) ON DELETE CASCADE,
    `user_id` INT NOT NULL REFERENCES `user` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `tournamentadmins`;
        ALTER TABLE `tournament` DROP COLUMN `players_per_match`;
        ALTER TABLE `tournament` DROP COLUMN `team_size`;
        ALTER TABLE `tournament` DROP COLUMN `is_active`;"""
