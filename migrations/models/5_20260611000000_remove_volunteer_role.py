from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DELETE FROM "userrole" WHERE "role" = 'volunteer';
        COMMENT ON COLUMN "userrole"."role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter
VOLUNTEER_COORDINATOR: volunteer_coordinator';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "userrole"."role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter
VOLUNTEER: volunteer
VOLUNTEER_COORDINATOR: volunteer_coordinator';"""
