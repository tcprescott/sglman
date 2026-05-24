from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `commentator`
            ADD COLUMN `acknowledged_at` DATETIME(6) NULL;
        ALTER TABLE `tracker`
            ADD COLUMN `acknowledged_at` DATETIME(6) NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `commentator`
            DROP COLUMN `acknowledged_at`;
        ALTER TABLE `tracker`
            DROP COLUMN `acknowledged_at`;"""
