from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `commentator`
            ADD COLUMN `acknowledged_at` DATETIME(6) NULL,
            ADD COLUMN `auto_acknowledged` BOOL NOT NULL DEFAULT 0;
        ALTER TABLE `tracker`
            ADD COLUMN `acknowledged_at` DATETIME(6) NULL,
            ADD COLUMN `auto_acknowledged` BOOL NOT NULL DEFAULT 0;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `commentator`
            DROP COLUMN `acknowledged_at`,
            DROP COLUMN `auto_acknowledged`;
        ALTER TABLE `tracker`
            DROP COLUMN `acknowledged_at`,
            DROP COLUMN `auto_acknowledged`;"""
