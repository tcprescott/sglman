from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "tenantjoinrequest" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "status" VARCHAR(20) NOT NULL DEFAULT 'pending',
    "message" VARCHAR(500),
    "decided_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "decided_by_id" INT REFERENCES "user" ("id") ON DELETE SET NULL,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_tenantjoinr_user_id_6ab341" UNIQUE ("user_id", "tenant_id")
);
CREATE INDEX IF NOT EXISTS "idx_tenantjoinr_tenant__49a444" ON "tenantjoinrequest" ("tenant_id", "status");
COMMENT ON COLUMN "tenantjoinrequest"."status" IS 'PENDING: pending\nAPPROVED: approved\nDENIED: denied';
COMMENT ON TABLE "tenantjoinrequest" IS 'Someone asking to join a community they can see the door of.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "tenantjoinrequest";"""
