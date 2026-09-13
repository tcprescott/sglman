from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "match" ADD "preset_override" VARCHAR(16);
        CREATE TABLE IF NOT EXISTS "matchhardpresetoptin" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "match_id" INT NOT NULL REFERENCES "match" ("id") ON DELETE CASCADE,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_matchhardpr_match_i_47a244" UNIQUE ("match_id", "user_id")
);
COMMENT ON COLUMN "match"."preset_override" IS 'HARD: hard\nSTANDARD: standard';
COMMENT ON TABLE "matchhardpresetoptin" IS 'One player privately agreeing to play their match on the harder preset.';
        ALTER TABLE "tournament" ADD "hard_preset_id" INT;
        ALTER TABLE "tournament" ADD CONSTRAINT "fk_tourname_preset_532a62ee" FOREIGN KEY ("hard_preset_id") REFERENCES "preset" ("id") ON DELETE SET NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" DROP CONSTRAINT IF EXISTS "fk_tourname_preset_532a62ee";
        ALTER TABLE "match" DROP COLUMN "preset_override";
        ALTER TABLE "tournament" DROP COLUMN "hard_preset_id";
        DROP TABLE IF EXISTS "matchhardpresetoptin";"""
