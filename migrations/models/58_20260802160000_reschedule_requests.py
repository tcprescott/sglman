from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "matchreschedulerequest" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "kind" VARCHAR(20) NOT NULL DEFAULT 'reschedule',
    "proposed_at" TIMESTAMPTZ,
    "reason" TEXT NOT NULL,
    "original_scheduled_at" TIMESTAMPTZ,
    "opponent_agreed_at" TIMESTAMPTZ,
    "status" VARCHAR(20) NOT NULL DEFAULT 'pending',
    "decided_at" TIMESTAMPTZ,
    "decision_note" TEXT,
    "decided_by_id" INT REFERENCES "user" ("id") ON DELETE SET NULL,
    "match_id" INT NOT NULL REFERENCES "match" ("id") ON DELETE CASCADE,
    "requested_by_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE
);
        CREATE INDEX IF NOT EXISTS "idx_matchresche_match_i_4d7c82" ON "matchreschedulerequest" ("match_id", "status");
        CREATE INDEX IF NOT EXISTS "idx_matchresche_status_1a9f03" ON "matchreschedulerequest" ("status");
        ALTER TABLE "tournament" ADD "allow_reschedule_requests" BOOL NOT NULL DEFAULT True;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "allow_reschedule_requests";
        DROP TABLE IF EXISTS "matchreschedulerequest";"""
