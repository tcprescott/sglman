from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "discordrolemapping"."app_role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter
VOLUNTEER_COORDINATOR: volunteer_coordinator
EQUIPMENT_MANAGER: equipment_manager
VOLUNTEER: volunteer';
        CREATE TABLE IF NOT EXISTS "equipment" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "asset_number" INT NOT NULL UNIQUE,
    "name" VARCHAR(255) NOT NULL,
    "description" TEXT,
    "private_notes" TEXT,
    "status" VARCHAR(20) NOT NULL DEFAULT 'available',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "owner_user_id" INT REFERENCES "user" ("id") ON DELETE SET NULL
);
COMMENT ON COLUMN "equipment"."status" IS 'AVAILABLE: available\nCHECKED_OUT: checked_out\nRETIRED: retired';
COMMENT ON TABLE "equipment" IS 'A physical asset available for lending at live events.';
        CREATE TABLE IF NOT EXISTS "equipmentloan" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "checked_out_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "checked_in_at" TIMESTAMPTZ,
    "borrower_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "checked_in_by_id" INT REFERENCES "user" ("id") ON DELETE CASCADE,
    "checked_out_by_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    "equipment_id" INT NOT NULL REFERENCES "equipment" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "equipmentloan" IS 'A single checkout of an :class:`Equipment` asset.';
        COMMENT ON COLUMN "userrole"."role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter
VOLUNTEER_COORDINATOR: volunteer_coordinator
EQUIPMENT_MANAGER: equipment_manager
VOLUNTEER: volunteer';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "userrole"."role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter
VOLUNTEER_COORDINATOR: volunteer_coordinator';
        COMMENT ON COLUMN "discordrolemapping"."app_role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter
VOLUNTEER_COORDINATOR: volunteer_coordinator';
        DROP TABLE IF EXISTS "equipmentloan";
        DROP TABLE IF EXISTS "equipment";"""
