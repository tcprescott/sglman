from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" DROP COLUMN "staff_administered";
        ALTER TABLE "tournament" DROP COLUMN "team_size";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" ADD "staff_administered" BOOL NOT NULL DEFAULT False;
        ALTER TABLE "tournament" ADD "team_size" INT NOT NULL DEFAULT 1;"""
