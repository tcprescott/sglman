from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `generatedseeds` DROP FOREIGN KEY `fk_generate_tourname_c5dd39bb`;
        ALTER TABLE `generatedseeds` ADD `seed_info` LONGTEXT;
        ALTER TABLE `generatedseeds` DROP COLUMN `tournament_id`;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `generatedseeds` ADD `tournament_id` INT NOT NULL;
        ALTER TABLE `generatedseeds` DROP COLUMN `seed_info`;
        ALTER TABLE `generatedseeds` ADD CONSTRAINT `fk_generate_tourname_c5dd39bb` FOREIGN KEY (`tournament_id`) REFERENCES `tournament` (`id`) ON DELETE CASCADE;"""
