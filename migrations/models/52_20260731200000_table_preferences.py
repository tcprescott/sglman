"""Per-user table layout preferences.

Deliberately global — no ``tenant_id``. Which columns a person wants on a board
is a property of the table, not of the community whose rows fill it, so someone
who is staff in two communities carries one answer between them (the same call
``User.timezone`` makes).

Hand-written to keep the numbered chain contiguous; the statements are idempotent.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "usertablepreference" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "table_key" VARCHAR(64) NOT NULL,
    "config" JSONB NOT NULL,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_usertablep_user_id_table_key" UNIQUE ("user_id", "table_key")
);
COMMENT ON TABLE "usertablepreference" IS 'One person''s saved layout for one table.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "usertablepreference";"""
