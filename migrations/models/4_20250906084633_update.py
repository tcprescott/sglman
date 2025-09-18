from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `match` DROP FOREIGN KEY `fk_match_user_33c2f273`;
        ALTER TABLE `match` DROP FOREIGN KEY `fk_match_user_7ad4a98a`;
        ALTER TABLE `match` DROP FOREIGN KEY `fk_match_user_99d7f3e1`;
        ALTER TABLE `match` DROP FOREIGN KEY `fk_match_user_dfa26317`;
        ALTER TABLE `match` DROP COLUMN `player4_id`;
        ALTER TABLE `match` DROP COLUMN `player_count`;
        ALTER TABLE `match` DROP COLUMN `score1`;
        ALTER TABLE `match` DROP COLUMN `score2`;
        ALTER TABLE `match` DROP COLUMN `player3_id`;
        ALTER TABLE `match` DROP COLUMN `player1_id`;
        ALTER TABLE `match` DROP COLUMN `player2_id`;
        CREATE TABLE IF NOT EXISTS `matchplayers` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `confirmed` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `match_id` INT NOT NULL,
    `user_id` INT NOT NULL,
    CONSTRAINT `fk_matchpla_match_185e9428` FOREIGN KEY (`match_id`) REFERENCES `match` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_matchpla_user_6691ebdd` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `team` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(255) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `tournament_id` INT NOT NULL,
    CONSTRAINT `fk_team_tourname_6215f9d8` FOREIGN KEY (`tournament_id`) REFERENCES `tournament` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `userteams` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `team_id` INT NOT NULL,
    `user_id` INT NOT NULL,
    CONSTRAINT `fk_userteam_team_a850ebd3` FOREIGN KEY (`team_id`) REFERENCES `team` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_userteam_user_43ab9735` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
        DROP TABLE IF EXISTS `matchconfirmations`;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `match` ADD `player4_id` INT;
        ALTER TABLE `match` ADD `player_count` INT NOT NULL DEFAULT 2;
        ALTER TABLE `match` ADD `score1` INT;
        ALTER TABLE `match` ADD `score2` INT;
        ALTER TABLE `match` ADD `player3_id` INT;
        ALTER TABLE `match` ADD `player1_id` INT NOT NULL;
        ALTER TABLE `match` ADD `player2_id` INT NOT NULL;
        DROP TABLE IF EXISTS `matchplayers`;
        DROP TABLE IF EXISTS `userteams`;
        DROP TABLE IF EXISTS `team`;
        ALTER TABLE `match` ADD CONSTRAINT `fk_match_user_dfa26317` FOREIGN KEY (`player1_id`) REFERENCES `user` (`id`) ON DELETE CASCADE;
        ALTER TABLE `match` ADD CONSTRAINT `fk_match_user_99d7f3e1` FOREIGN KEY (`player4_id`) REFERENCES `user` (`id`) ON DELETE CASCADE;
        ALTER TABLE `match` ADD CONSTRAINT `fk_match_user_7ad4a98a` FOREIGN KEY (`player3_id`) REFERENCES `user` (`id`) ON DELETE CASCADE;
        ALTER TABLE `match` ADD CONSTRAINT `fk_match_user_33c2f273` FOREIGN KEY (`player2_id`) REFERENCES `user` (`id`) ON DELETE CASCADE;"""
