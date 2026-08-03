from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" ADD "prize_pool" DECIMAL(10,2);
        ALTER TABLE "tournament" ADD "prize_bonus" DECIMAL(10,2);
        CREATE TABLE IF NOT EXISTS "tournamentpayout" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "place" INT NOT NULL,
    "percentage" DECIMAL(5,2) NOT NULL,
    "note" VARCHAR(255),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "entrant_id" INT REFERENCES "user" ("id") ON DELETE SET NULL,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    "tournament_id" INT NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_tournamentp_tournam_a9fe44" UNIQUE ("tournament_id", "place", "entrant_id")
);
CREATE INDEX IF NOT EXISTS "idx_tournamentp_tournam_d9485f" ON "tournamentpayout" ("tournament_id");
COMMENT ON TABLE "tournamentpayout" IS 'One placement''s share of a tournament''s prize pool.';
        ALTER TABLE "user" ADD "matcherino_username" VARCHAR(255);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "user" DROP COLUMN "matcherino_username";
        ALTER TABLE "tournament" DROP COLUMN "prize_pool";
        ALTER TABLE "tournament" DROP COLUMN "prize_bonus";
        DROP TABLE IF EXISTS "tournamentpayout";"""
