from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `triforcetext` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `text` VARCHAR(200) NOT NULL,
            `author` VARCHAR(200),
            `approved` BOOL,
            `approved_at` DATETIME(6),
            `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `approved_by_id` INT,
            `tournament_id` INT NOT NULL,
            `user_id` INT,
            CONSTRAINT `fk_triforce_approver` FOREIGN KEY (`approved_by_id`) REFERENCES `user` (`id`) ON DELETE SET NULL,
            CONSTRAINT `fk_triforce_tournament` FOREIGN KEY (`tournament_id`) REFERENCES `tournament` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_triforce_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE SET NULL,
            KEY `idx_triforce_tournament_approved` (`tournament_id`, `approved`)
        ) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `triforcetext`;"""
