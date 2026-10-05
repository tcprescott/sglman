from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "checkinevent" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "matcherino_bounty_id" INT,
    "status" VARCHAR(16) NOT NULL DEFAULT 'draft',
    "sync_interval_minutes" INT NOT NULL DEFAULT 5,
    "last_synced_at" TIMESTAMPTZ,
    "last_sync_error" TEXT,
    "last_sync_count" INT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_checkineven_tenant__02fb71" UNIQUE ("tenant_id", "matcherino_bounty_id")
);
COMMENT ON COLUMN "checkinevent"."status" IS 'DRAFT: draft\nOPEN: open\nCLOSED: closed';
COMMENT ON TABLE "checkinevent" IS 'An in-person event whose attendees are checked in at a desk.';
        COMMENT ON COLUMN "discordrolemapping"."app_role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter
VOLUNTEER_COORDINATOR: volunteer_coordinator
EQUIPMENT_MANAGER: equipment_manager
VOLUNTEER: volunteer
CHECK_IN_DESK: check_in_desk
PRESET_MANAGER: preset_manager
SYNC_ADMIN: sync_admin
QUALIFIER_ADMIN: qualifier_admin
SUPER_ADMIN: super_admin';
        ALTER TABLE "user" ADD "matcherino_user_id" VARCHAR(64) UNIQUE;
        COMMENT ON COLUMN "userrole"."role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter
VOLUNTEER_COORDINATOR: volunteer_coordinator
EQUIPMENT_MANAGER: equipment_manager
VOLUNTEER: volunteer
CHECK_IN_DESK: check_in_desk
PRESET_MANAGER: preset_manager
SYNC_ADMIN: sync_admin
QUALIFIER_ADMIN: qualifier_admin
SUPER_ADMIN: super_admin';
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_user_matcher_87eedf" ON "user" ("matcherino_user_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uid_user_matcher_87eedf";
        ALTER TABLE "user" DROP COLUMN "matcherino_user_id";
        COMMENT ON COLUMN "userrole"."role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter
VOLUNTEER_COORDINATOR: volunteer_coordinator
EQUIPMENT_MANAGER: equipment_manager
VOLUNTEER: volunteer
PRESET_MANAGER: preset_manager
SYNC_ADMIN: sync_admin
QUALIFIER_ADMIN: qualifier_admin
SUPER_ADMIN: super_admin';
        COMMENT ON COLUMN "discordrolemapping"."app_role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter
VOLUNTEER_COORDINATOR: volunteer_coordinator
EQUIPMENT_MANAGER: equipment_manager
VOLUNTEER: volunteer
PRESET_MANAGER: preset_manager
SYNC_ADMIN: sync_admin
QUALIFIER_ADMIN: qualifier_admin
SUPER_ADMIN: super_admin';
        DROP TABLE IF EXISTS "checkinevent";"""
