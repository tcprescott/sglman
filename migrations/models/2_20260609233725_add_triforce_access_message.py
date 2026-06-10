from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" ADD "triforce_access_message" TEXT;
        COMMENT ON COLUMN "userrole"."role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager
TRIFORCE_SUBMITTER: triforce_submitter';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "userrole"."role" IS 'STAFF: staff
PROCTOR: proctor
STREAM_MANAGER: stream_manager';
        ALTER TABLE "tournament" DROP COLUMN "triforce_access_message";"""
