from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `user` DROP COLUMN `permission`;
        CREATE TABLE IF NOT EXISTS `userrole` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `role` VARCHAR(32) NOT NULL,
            `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `granted_by_id` INT,
            `user_id` INT NOT NULL,
            UNIQUE KEY `uid_userrole_user_role` (`user_id`, `role`),
            CONSTRAINT `fk_userrole_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
            CONSTRAINT `fk_userrole_granted_by` FOREIGN KEY (`granted_by_id`) REFERENCES `user` (`id`) ON DELETE SET NULL
        ) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `TournamentCrewCoordinators` (
            `tournament_id` INT NOT NULL,
            `user_id` INT NOT NULL,
            FOREIGN KEY (`tournament_id`) REFERENCES `tournament` (`id`) ON DELETE CASCADE,
            FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
            UNIQUE KEY `uidx_TournamentCC_tournament_user` (`tournament_id`, `user_id`)
        ) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `TournamentCrewCoordinators`;
        DROP TABLE IF EXISTS `userrole`;
        ALTER TABLE `user` ADD `permission` SMALLINT NOT NULL DEFAULT 0;"""
