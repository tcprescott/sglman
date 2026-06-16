from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "feedback" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "category" VARCHAR(20) NOT NULL DEFAULT 'other',
    "message" TEXT NOT NULL,
    "page_url" VARCHAR(512) NOT NULL,
    "status" VARCHAR(20) NOT NULL DEFAULT 'new',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
COMMENT ON COLUMN "feedback"."category" IS 'BUG: bug\nSUGGESTION: suggestion\nPRAISE: praise\nOTHER: other';
COMMENT ON COLUMN "feedback"."status" IS 'NEW: new\nREVIEWED: reviewed';
COMMENT ON TABLE "feedback" IS 'An in-app feedback submission from a logged-in attendee.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "feedback";"""
