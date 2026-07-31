from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "asyncqualifierrun" ADD "expired_at" TIMESTAMPTZ;
        ALTER TABLE "asyncqualifierrun" ADD "expiry_warned_at" TIMESTAMPTZ;
        CREATE INDEX "idx_aqrun_status_started" ON "asyncqualifierrun" ("status", "started_at");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_aqrun_status_started";
        ALTER TABLE "asyncqualifierrun" DROP COLUMN "expiry_warned_at";
        ALTER TABLE "asyncqualifierrun" DROP COLUMN "expired_at";"""
