from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "match" ADD "needs_review" BOOL NOT NULL DEFAULT False;
        ALTER TABLE "match" ADD "review_note" TEXT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "match" DROP COLUMN "needs_review";
        ALTER TABLE "match" DROP COLUMN "review_note";"""
