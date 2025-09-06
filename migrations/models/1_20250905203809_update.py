from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
    SET FOREIGN_KEY_CHECKS=0;
        CREATE TABLE IF NOT EXISTS `auditlog` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `action` VARCHAR(255) NOT NULL,
    `details` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `user_id` INT NOT NULL,
    CONSTRAINT `fk_auditlog_user_2856f5a7` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `commentator` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `approved` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `approved_by_id` INT,
    `match_id` INT NOT NULL,
    `user_id` INT NOT NULL,
    CONSTRAINT `fk_commenta_user_15ed728b` FOREIGN KEY (`approved_by_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_commenta_match_25f0d1b7` FOREIGN KEY (`match_id`) REFERENCES `match` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_commenta_user_5a5049c6` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `match` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `player_count` INT NOT NULL DEFAULT 2,
    `score1` INT,
    `score2` INT,
    `scheduled_at` DATETIME(6),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `player1_id` INT NOT NULL,
    `player2_id` INT NOT NULL,
    `player3_id` INT,
    `player4_id` INT,
    `stream_room_id` INT,
    `tournament_id` INT NOT NULL,
    CONSTRAINT `fk_match_user_dfa26317` FOREIGN KEY (`player1_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_match_user_33c2f273` FOREIGN KEY (`player2_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_match_user_7ad4a98a` FOREIGN KEY (`player3_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_match_user_99d7f3e1` FOREIGN KEY (`player4_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_match_streamro_085cf0bb` FOREIGN KEY (`stream_room_id`) REFERENCES `streamroom` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_match_tourname_afaca194` FOREIGN KEY (`tournament_id`) REFERENCES `tournament` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `matchconfirmations` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `confirmed` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `match_id` INT NOT NULL,
    `user_id` INT NOT NULL,
    CONSTRAINT `fk_matchcon_match_9619ea34` FOREIGN KEY (`match_id`) REFERENCES `match` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_matchcon_user_255ba3fd` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `streamroom` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(255) NOT NULL UNIQUE,
    `stream_url` VARCHAR(255),
    `is_active` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `tournament` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(255) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `tracker` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `approved` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `approved_by_id` INT,
    `match_id` INT NOT NULL,
    `user_id` INT NOT NULL,
    CONSTRAINT `fk_tracker_user_db338c3e` FOREIGN KEY (`approved_by_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_tracker_match_8e8e1ede` FOREIGN KEY (`match_id`) REFERENCES `match` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_tracker_user_aa1b2669` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
        ALTER TABLE `user` ADD `permission` SMALLINT NOT NULL COMMENT 'USER: 0\nTOURNAMENT_ADMIN: 1\nSUPERADMIN: 2' DEFAULT 0;
        ALTER TABLE `user` RENAME COLUMN `discord_token` TO `access_token`;
        ALTER TABLE `user` ADD `username` VARCHAR(150) NOT NULL;
        ALTER TABLE `user` ADD `is_active` BOOL NOT NULL DEFAULT 1;
    SET FOREIGN_KEY_CHECKS=1;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """SET FOREIGN_KEY_CHECKS=0;
        ALTER TABLE `user` DROP INDEX `username`;
        ALTER TABLE `user` RENAME COLUMN `access_token` TO `discord_token`;
        ALTER TABLE `user` DROP COLUMN `permission`;
        ALTER TABLE `user` DROP COLUMN `username`;
        ALTER TABLE `user` DROP COLUMN `is_active`;
        DROP TABLE IF EXISTS `commentator`;
        DROP TABLE IF EXISTS `streamroom`;
        DROP TABLE IF EXISTS `tracker`;
        DROP TABLE IF EXISTS `match`;
        DROP TABLE IF EXISTS `tournament`;
        DROP TABLE IF EXISTS `auditlog`;
        DROP TABLE IF EXISTS `matchconfirmations`;
        SET FOREIGN_KEY_CHECKS=1;"""
