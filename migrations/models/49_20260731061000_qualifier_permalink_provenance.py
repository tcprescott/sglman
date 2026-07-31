from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "asyncqualifierpermalink" ADD "generated_seed_id" INT;
        ALTER TABLE "asyncqualifierpermalink" ADD CONSTRAINT "fk_aqpermalink_genseed" FOREIGN KEY ("generated_seed_id") REFERENCES "generatedseeds" ("id") ON DELETE SET NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "asyncqualifierpermalink" DROP CONSTRAINT IF EXISTS "fk_aqpermalink_genseed";
        ALTER TABLE "asyncqualifierpermalink" DROP COLUMN "generated_seed_id";"""
