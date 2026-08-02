from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "station" ADD "side" VARCHAR(10);
        ALTER TABLE "station" ADD "position" INT;
        COMMENT ON COLUMN "station"."side" IS 'LEFT: left\nRIGHT: right';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "station" DROP COLUMN "side";
        ALTER TABLE "station" DROP COLUMN "position";"""
