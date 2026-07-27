from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "randomizercredential" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "randomizer" VARCHAR(32) NOT NULL,
    "key" VARCHAR(64) NOT NULL,
    "value" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_randomizerc_tenant__bb0560" UNIQUE ("tenant_id", "randomizer", "key")
);
CREATE INDEX IF NOT EXISTS "idx_randomizerc_tenant__09fa83" ON "randomizercredential" ("tenant_id");
COMMENT ON TABLE "randomizercredential" IS 'A community''s own credential for one randomizer''s key-gated upstream API.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "randomizercredential";"""
