from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" ADD "required_commentators" INT NOT NULL DEFAULT 1;
        ALTER TABLE "tournament" ADD "required_trackers" INT NOT NULL DEFAULT 1;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" DROP COLUMN "required_commentators";
        ALTER TABLE "tournament" DROP COLUMN "required_trackers";"""
