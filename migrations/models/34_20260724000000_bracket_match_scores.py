from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "bracketmatch" ADD "entry1_score" INT;
        ALTER TABLE "bracketmatch" ADD "entry2_score" INT;
        ALTER TABLE "bracketmatch" ADD "forfeit" BOOL NOT NULL DEFAULT False;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "bracketmatch" DROP COLUMN "entry1_score";
        ALTER TABLE "bracketmatch" DROP COLUMN "entry2_score";
        ALTER TABLE "bracketmatch" DROP COLUMN "forfeit";"""
