from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "userrole"."source" IS 'MANUAL: manual
DISCORD: discord
VOLUNTEER: volunteer';
        CREATE TABLE IF NOT EXISTS "volunteerrolemapping" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "app_role" VARCHAR(32) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "position_id" INT NOT NULL REFERENCES "volunteerposition" ("id") ON DELETE CASCADE,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_volunteerro_tenant__b6752e" UNIQUE ("tenant_id", "position_id", "app_role")
);
COMMENT ON COLUMN "volunteerrolemapping"."app_role" IS 'STAFF: staff\nPROCTOR: proctor\nSTREAM_MANAGER: stream_manager\nTRIFORCE_SUBMITTER: triforce_submitter\nVOLUNTEER_COORDINATOR: volunteer_coordinator\nEQUIPMENT_MANAGER: equipment_manager\nVOLUNTEER: volunteer\nPRESET_MANAGER: preset_manager\nSYNC_ADMIN: sync_admin\nQUALIFIER_ADMIN: qualifier_admin\nSUPER_ADMIN: super_admin';
COMMENT ON TABLE "volunteerrolemapping" IS 'One volunteer position → one app role, held by anyone on its shifts.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "userrole"."source" IS 'MANUAL: manual
DISCORD: discord';
        DROP TABLE IF EXISTS "volunteerrolemapping";"""
