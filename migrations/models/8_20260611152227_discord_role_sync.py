from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "discordrolemapping" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "guild_id" BIGINT NOT NULL,
    "discord_role_id" BIGINT NOT NULL,
    "discord_role_name" VARCHAR(100) NOT NULL,
    "app_role" VARCHAR(32) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "uid_discordrole_guild_i_16fbfa" UNIQUE ("guild_id", "discord_role_id", "app_role")
);
COMMENT ON COLUMN "discordrolemapping"."app_role" IS 'STAFF: staff\nPROCTOR: proctor\nSTREAM_MANAGER: stream_manager\nTRIFORCE_SUBMITTER: triforce_submitter\nVOLUNTEER_COORDINATOR: volunteer_coordinator';
        ALTER TABLE "userrole" ADD "source" VARCHAR(16) NOT NULL DEFAULT 'manual';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "userrole" DROP COLUMN "source";
        DROP TABLE IF EXISTS "discordrolemapping";"""
