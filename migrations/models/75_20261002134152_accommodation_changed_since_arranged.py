from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "accommodation_request" ADD "arranged_details" TEXT;
        ALTER TABLE "accommodation_request" ADD "changed_since_arranged" BOOL NOT NULL DEFAULT False;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "accommodation_request" DROP COLUMN "arranged_details";
        ALTER TABLE "accommodation_request" DROP COLUMN "changed_since_arranged";"""
