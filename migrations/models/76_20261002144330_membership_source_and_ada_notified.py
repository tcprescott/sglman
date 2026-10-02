from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "accommodation_request" ADD "staff_notified_at" TIMESTAMPTZ;
        ALTER TABLE "tenantmembership" ADD "source" VARCHAR(32);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tenantmembership" DROP COLUMN "source";
        ALTER TABLE "accommodation_request" DROP COLUMN "staff_notified_at";"""
