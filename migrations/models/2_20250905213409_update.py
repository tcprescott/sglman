from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `generatedseeds` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `seed_url` VARCHAR(255) NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `tournament_id` INT NOT NULL,
    CONSTRAINT `fk_generate_tourname_c5dd39bb` FOREIGN KEY (`tournament_id`) REFERENCES `tournament` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
        ALTER TABLE `match` ADD `generated_seed_id` INT;
        ALTER TABLE `match` ADD `started_at` DATETIME(6);
        ALTER TABLE `match` ADD CONSTRAINT `fk_match_generate_e3642639` FOREIGN KEY (`generated_seed_id`) REFERENCES `generatedseeds` (`id`) ON DELETE CASCADE;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `match` DROP FOREIGN KEY `fk_match_generate_e3642639`;
        ALTER TABLE `match` DROP COLUMN `generated_seed_id`;
        ALTER TABLE `match` DROP COLUMN `started_at`;
        DROP TABLE IF EXISTS `generatedseeds`;"""
