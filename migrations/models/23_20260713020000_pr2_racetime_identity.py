"""Racetime identity link (PR 2): ``user`` racetime identity columns.

Additive, idempotent. Mirrors the Twitch link (migration 17): identity only —
``racetime_user_id`` (unique, so a racetime id resolves to exactly one user),
cached ``racetime_username``, and ``racetime_linked_at``. No access token is
persisted. Postgres allows multiple NULLs under a unique index, so unlinked
users stay unconstrained.

Hand-written (like migrations 14/18-22) to keep the numbered chain contiguous;
every statement is idempotent.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "racetime_user_id" VARCHAR(64);
        ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "racetime_username" VARCHAR(255);
        ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "racetime_linked_at" TIMESTAMPTZ;
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_user_racetime_user_id"
            ON "user" ("racetime_user_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uid_user_racetime_user_id";
        ALTER TABLE "user" DROP COLUMN IF EXISTS "racetime_user_id";
        ALTER TABLE "user" DROP COLUMN IF EXISTS "racetime_username";
        ALTER TABLE "user" DROP COLUMN IF EXISTS "racetime_linked_at";"""
