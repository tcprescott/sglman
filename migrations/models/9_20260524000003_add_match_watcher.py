from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `matchwatcher` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            `match_id` INT NOT NULL,
            `user_id` INT NOT NULL,
            UNIQUE KEY `uid_matchwatcher_user_match` (`user_id`, `match_id`),
            CONSTRAINT `fk_matchwatcher_match` FOREIGN KEY (`match_id`) REFERENCES `match` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_matchwatcher_user`  FOREIGN KEY (`user_id`)  REFERENCES `user` (`id`) ON DELETE CASCADE
        ) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `matchwatcher`;"""
