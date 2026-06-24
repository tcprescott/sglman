from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "volunteerassignment"
            ADD COLUMN "checked_in_at" TIMESTAMPTZ NULL,
            ADD COLUMN "checked_in_by_id" INT NULL REFERENCES "user" ("id") ON DELETE SET NULL;
        COMMENT ON COLUMN "userrole"."role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter
VOLUNTEER_COORDINATOR: volunteer_coordinator
EQUIPMENT_MANAGER: equipment_manager
VOLUNTEER: volunteer';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "volunteerassignment"
            DROP COLUMN IF EXISTS "checked_in_at",
            DROP COLUMN IF EXISTS "checked_in_by_id";
        COMMENT ON COLUMN "userrole"."role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter
VOLUNTEER_COORDINATOR: volunteer_coordinator
EQUIPMENT_MANAGER: equipment_manager';"""
