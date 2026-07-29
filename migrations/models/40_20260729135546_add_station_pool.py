from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "station" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(50) NOT NULL,
    "section" VARCHAR(50),
    "sort_order" INT NOT NULL DEFAULT 0,
    "is_active" BOOL NOT NULL DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_station_tenant__a39231" UNIQUE ("tenant_id", "name")
);
COMMENT ON TABLE "station" IS 'A physical seat/setup in the venue a match player can be assigned to.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "station";"""
