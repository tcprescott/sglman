from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "userrole"."role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter
VOLUNTEER: volunteer
VOLUNTEER_COORDINATOR: volunteer_coordinator';
        CREATE TABLE IF NOT EXISTS "volunteerposition" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL UNIQUE,
    "description" TEXT,
    "color" VARCHAR(32),
    "display_order" INT NOT NULL DEFAULT 0,
    "is_active" BOOL NOT NULL DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE "volunteerposition" IS 'A coordinator-defined volunteer job (e.g. Check-in Desk, Race Proctor).';
        CREATE TABLE IF NOT EXISTS "volunteerprofile" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "opted_in_at" TIMESTAMPTZ,
    "note" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL UNIQUE REFERENCES "user" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "volunteerprofile" IS 'Per-user opt-in record for onsite volunteering.';
        CREATE TABLE IF NOT EXISTS "volunteershift" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "starts_at" TIMESTAMPTZ NOT NULL,
    "ends_at" TIMESTAMPTZ NOT NULL,
    "label" VARCHAR(100),
    "slots_needed" INT NOT NULL DEFAULT 1,
    "notes" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "position_id" INT NOT NULL REFERENCES "volunteerposition" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_volunteersh_starts__276d02" ON "volunteershift" ("starts_at");
COMMENT ON TABLE "volunteershift" IS 'A fillable slot-set for a position over a time window (UTC).';
        CREATE TABLE IF NOT EXISTS "volunteerassignment" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "auto_generated" BOOL NOT NULL DEFAULT False,
    "acknowledged_at" TIMESTAMPTZ,
    "reminder_sent_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "assigned_by_id" INT REFERENCES "user" ("id") ON DELETE SET NULL,
    "shift_id" INT NOT NULL REFERENCES "volunteershift" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_volunteeras_shift_i_7cb1af" UNIQUE ("shift_id", "user_id")
);
COMMENT ON TABLE "volunteerassignment" IS 'A volunteer placed into a shift.';
        CREATE TABLE IF NOT EXISTS "volunteerqualification" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "position_id" INT NOT NULL REFERENCES "volunteerposition" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_volunteerqu_user_id_72ea23" UNIQUE ("user_id", "position_id")
);
COMMENT ON TABLE "volunteerqualification" IS 'Capability matrix: which positions a user can fill.';
        CREATE TABLE IF NOT EXISTS "volunteeravailability" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "starts_at" TIMESTAMPTZ NOT NULL,
    "ends_at" TIMESTAMPTZ NOT NULL,
    "status" VARCHAR(20) NOT NULL DEFAULT 'available',
    "note" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_volunteerav_starts__98dc8c" ON "volunteeravailability" ("starts_at");
COMMENT ON COLUMN "volunteeravailability"."status" IS 'AVAILABLE: available\nUNAVAILABLE: unavailable\nPREFERRED: preferred';
COMMENT ON TABLE "volunteeravailability" IS 'A window a volunteer self-declares (UTC).';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "userrole"."role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter';
        DROP TABLE IF EXISTS "volunteerprofile";
        DROP TABLE IF EXISTS "volunteeravailability";
        DROP TABLE IF EXISTS "volunteerposition";
        DROP TABLE IF EXISTS "volunteerqualification";
        DROP TABLE IF EXISTS "volunteershift";
        DROP TABLE IF EXISTS "volunteerassignment";"""
