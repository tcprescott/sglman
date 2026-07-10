"""Add the telemetryevent table (engagement telemetry).

Append-only behavioral log, sibling to auditlog. ``user_id`` is nullable with
``ON DELETE SET NULL`` so the trail survives user deletion; indexes cover the
report's hot paths (time range, per-user, per-category, per-event, and session
reconstruction). Hand-written to keep the numbered chain contiguous with the
model added to ``models.py``.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "telemetryevent" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "category" VARCHAR(32) NOT NULL,
    "event_type" VARCHAR(100) NOT NULL,
    "path" VARCHAR(512),
    "session_id" VARCHAR(64),
    "details" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT REFERENCES "user" ("id") ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS "idx_telemetryev_created_at" ON "telemetryevent" ("created_at");
CREATE INDEX IF NOT EXISTS "idx_telemetryev_category" ON "telemetryevent" ("category");
CREATE INDEX IF NOT EXISTS "idx_telemetryev_event_type" ON "telemetryevent" ("event_type");
CREATE INDEX IF NOT EXISTS "idx_telemetryev_session_id" ON "telemetryevent" ("session_id");
CREATE INDEX IF NOT EXISTS "idx_telemetryev_user_id" ON "telemetryevent" ("user_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "telemetryevent";"""
