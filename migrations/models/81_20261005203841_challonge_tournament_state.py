from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" ADD "challonge_state" VARCHAR(32);
        ALTER TABLE "tournament" ADD "challonge_group_stage" BOOL NOT NULL DEFAULT False;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" DROP COLUMN "challonge_state";
        ALTER TABLE "tournament" DROP COLUMN "challonge_group_stage";"""
