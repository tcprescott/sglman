from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `matchacknowledgment` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `acknowledged_at` DATETIME(6),
            `auto_acknowledged` BOOL NOT NULL DEFAULT 0,
            `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `match_id` INT NOT NULL,
            `user_id` INT NOT NULL,
            UNIQUE KEY `uidx_matchack_match_user` (`match_id`, `user_id`),
            CONSTRAINT `fk_matchack_match` FOREIGN KEY (`match_id`) REFERENCES `match` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_matchack_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `matchacknowledgment`;"""
