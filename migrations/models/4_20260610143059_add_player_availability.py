from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "playeravailability" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "starts_at" TIMESTAMPTZ NOT NULL,
    "ends_at" TIMESTAMPTZ NOT NULL,
    "status" VARCHAR(20) NOT NULL DEFAULT 'available',
    "note" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_playeravail_starts__87c320" ON "playeravailability" ("starts_at");
COMMENT ON COLUMN "playeravailability"."status" IS 'AVAILABLE: available\nUNAVAILABLE: unavailable\nPREFERRED: preferred';
COMMENT ON TABLE "playeravailability" IS 'A window a player self-declares they can play (UTC).';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "playeravailability";"""
