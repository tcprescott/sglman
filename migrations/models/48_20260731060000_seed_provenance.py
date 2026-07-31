from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "generatedseeds" ADD "randomizer" VARCHAR(32);
        ALTER TABLE "generatedseeds" ADD "settings_snapshot" JSONB;
        ALTER TABLE "generatedseeds" ADD "provider_meta" JSONB;
        ALTER TABLE "generatedseeds" ADD "preset_id" INT;
        ALTER TABLE "generatedseeds" ADD "rolled_by_id" INT;
        ALTER TABLE "generatedseeds" ADD CONSTRAINT "fk_genseed_preset" FOREIGN KEY ("preset_id") REFERENCES "preset" ("id") ON DELETE SET NULL;
        ALTER TABLE "generatedseeds" ADD CONSTRAINT "fk_genseed_rolled_by" FOREIGN KEY ("rolled_by_id") REFERENCES "user" ("id") ON DELETE SET NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "generatedseeds" DROP CONSTRAINT IF EXISTS "fk_genseed_rolled_by";
        ALTER TABLE "generatedseeds" DROP CONSTRAINT IF EXISTS "fk_genseed_preset";
        ALTER TABLE "generatedseeds" DROP COLUMN "rolled_by_id";
        ALTER TABLE "generatedseeds" DROP COLUMN "preset_id";
        ALTER TABLE "generatedseeds" DROP COLUMN "provider_meta";
        ALTER TABLE "generatedseeds" DROP COLUMN "settings_snapshot";
        ALTER TABLE "generatedseeds" DROP COLUMN "randomizer";"""
