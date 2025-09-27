from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `generatedseeds` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `seed_url` VARCHAR(255) NOT NULL,
    `seed_info` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `streamroom` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(255) NOT NULL UNIQUE,
    `stream_url` VARCHAR(255),
    `is_active` BOOL NOT NULL DEFAULT 1,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `systemconfiguration` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(255) NOT NULL UNIQUE,
    `value` LONGTEXT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `testmodel` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(255) NOT NULL,
    `description` LONGTEXT NOT NULL,
    `value` INT NOT NULL,
    `somethingelse` VARCHAR(255) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `tournament` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(255) NOT NULL,
    `description` LONGTEXT,
    `seed_generator` VARCHAR(255),
    `is_active` BOOL NOT NULL DEFAULT 1,
    `players_per_match` INT NOT NULL DEFAULT 2,
    `team_size` INT NOT NULL DEFAULT 1,
    `bracket_url` VARCHAR(255),
    `rules_url` VARCHAR(255),
    `tournament_format` VARCHAR(255),
    `average_match_duration` INT,
    `max_match_duration` INT,
    `staff_administered` BOOL NOT NULL DEFAULT 0,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `match` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `scheduled_at` DATETIME(6),
    `seated_at` DATETIME(6),
    `finished_at` DATETIME(6),
    `comment` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `generated_seed_id` INT,
    `stream_room_id` INT,
    `tournament_id` INT NOT NULL,
    CONSTRAINT `fk_match_generate_e3642639` FOREIGN KEY (`generated_seed_id`) REFERENCES `generatedseeds` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_match_streamro_085cf0bb` FOREIGN KEY (`stream_room_id`) REFERENCES `streamroom` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_match_tourname_afaca194` FOREIGN KEY (`tournament_id`) REFERENCES `tournament` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `team` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` VARCHAR(255) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `tournament_id` INT NOT NULL,
    CONSTRAINT `fk_team_tourname_6215f9d8` FOREIGN KEY (`tournament_id`) REFERENCES `tournament` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `user` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `discord_id` BIGINT NOT NULL UNIQUE,
    `access_token` VARCHAR(255),
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `username` VARCHAR(150) NOT NULL,
    `display_name` VARCHAR(150),
    `pronouns` VARCHAR(50),
    `is_active` BOOL NOT NULL DEFAULT 1,
    `permission` SMALLINT NOT NULL COMMENT 'USER: 0\nTOURNAMENT_ADMIN: 1\nSUPERADMIN: 2' DEFAULT 0
) CHARACTER SET utf8mb4;
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
CREATE TABLE IF NOT EXISTS `tournamentplayers` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `tournament_id` INT NOT NULL,
    `user_id` INT NOT NULL,
    CONSTRAINT `fk_tourname_tourname_ceef4cf1` FOREIGN KEY (`tournament_id`) REFERENCES `tournament` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_tourname_user_a020f564` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
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
CREATE TABLE IF NOT EXISTS `userteams` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `team_id` INT NOT NULL,
    `user_id` INT NOT NULL,
    CONSTRAINT `fk_userteam_team_a850ebd3` FOREIGN KEY (`team_id`) REFERENCES `team` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_userteam_user_43ab9735` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `aerich` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `version` VARCHAR(255) NOT NULL,
    `app` VARCHAR(100) NOT NULL,
    `content` JSON NOT NULL
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `TournamentAdmins` (
    `tournament_id` INT NOT NULL,
    `user_id` INT NOT NULL,
    FOREIGN KEY (`tournament_id`) REFERENCES `tournament` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
    UNIQUE KEY `uidx_TournamentA_tournam_ede4d6` (`tournament_id`, `user_id`)
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
