from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `match` ADD `is_stream_candidate` BOOL NOT NULL DEFAULT 0;
        CREATE TABLE IF NOT EXISTS `tournamentnotificationpreference` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `match_notifications` VARCHAR(30) NOT NULL DEFAULT 'none',
            `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `tournament_id` INT NOT NULL REFERENCES `tournament` (`id`) ON DELETE CASCADE,
            `user_id` INT NOT NULL REFERENCES `user` (`id`) ON DELETE CASCADE,
            UNIQUE KEY `uid_tournamentno_user_tournament` (`user_id`, `tournament_id`)
        ) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `tournamentnotificationpreference`;
        ALTER TABLE `match` DROP COLUMN `is_stream_candidate`;"""
