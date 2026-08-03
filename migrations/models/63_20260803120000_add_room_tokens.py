from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "roomtoken" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "label" VARCHAR(100) NOT NULL,
    "token_hash" VARCHAR(64) NOT NULL UNIQUE,
    "last_used_at" TIMESTAMPTZ,
    "revoked_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by_id" INT REFERENCES "user" ("id") ON DELETE SET NULL,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_roomtoken_token_h_0c4b1a" ON "roomtoken" ("token_hash");
CREATE INDEX IF NOT EXISTS "idx_roomtoken_tenant__7f2d33" ON "roomtoken" ("tenant_id");
COMMENT ON TABLE "roomtoken" IS 'An unlisted key that opens one read-only page on a shared venue machine.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "roomtoken";"""
