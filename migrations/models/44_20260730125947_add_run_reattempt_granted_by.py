from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "asyncqualifierrun" ADD "reattempt_granted_by_id" INT;
        ALTER TABLE "asyncqualifierrun" ADD CONSTRAINT "fk_asyncqua_user_65c594c6" FOREIGN KEY ("reattempt_granted_by_id") REFERENCES "user" ("id") ON DELETE SET NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "asyncqualifierrun" DROP CONSTRAINT IF EXISTS "fk_asyncqua_user_65c594c6";
        ALTER TABLE "asyncqualifierrun" DROP COLUMN "reattempt_granted_by_id";"""
