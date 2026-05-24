from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `match` ADD `is_stream_candidate` BOOL NOT NULL DEFAULT 0;
        CREATE TABLE IF NOT EXISTS `tournamentnotificationpreference` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `match_notifications` VARCHAR(30) NOT NULL DEFAULT 'none',
            `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `tournament_id` INT NOT NULL,
            `user_id` INT NOT NULL,
            UNIQUE KEY `uid_tournamentno_user_tournament` (`user_id`, `tournament_id`),
            INDEX `idx_tournamentno_tournament_level` (`tournament_id`, `match_notifications`),
            CONSTRAINT `fk_tnp_tournament` FOREIGN KEY (`tournament_id`) REFERENCES `tournament` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_tnp_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `tournamentnotificationpreference`;
        ALTER TABLE `match` DROP COLUMN `is_stream_candidate`;"""
