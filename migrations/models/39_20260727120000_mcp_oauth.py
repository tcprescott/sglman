from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "mcpoauthclient" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "client_id" VARCHAR(64) NOT NULL UNIQUE,
    "client_name" VARCHAR(255) NOT NULL,
    "redirect_uris" JSONB NOT NULL,
    "grant_types" JSONB NOT NULL,
    "response_types" JSONB NOT NULL,
    "token_endpoint_auth_method" VARCHAR(32) NOT NULL DEFAULT 'none',
    "scope" VARCHAR(255),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "idx_mcpoauthcli_client__cf875d" ON "mcpoauthclient" ("client_id");
COMMENT ON TABLE "mcpoauthclient" IS 'An MCP client registered through RFC 7591 dynamic client registration.';
CREATE TABLE IF NOT EXISTS "mcpauthorizationcode" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "code_hash" VARCHAR(64) NOT NULL UNIQUE,
    "redirect_uri" VARCHAR(2048) NOT NULL,
    "redirect_uri_provided_explicitly" BOOL NOT NULL DEFAULT True,
    "code_challenge" VARCHAR(128) NOT NULL,
    "code_challenge_method" VARCHAR(8) NOT NULL DEFAULT 'S256',
    "scope" VARCHAR(255),
    "resource" VARCHAR(2048),
    "expires_at" TIMESTAMPTZ NOT NULL,
    "consumed_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "client_id" INT NOT NULL REFERENCES "mcpoauthclient" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_mcpauthoriz_code_ha_7472c2" ON "mcpauthorizationcode" ("code_hash");
COMMENT ON TABLE "mcpauthorizationcode" IS 'A single-use authorization code awaiting exchange at the token endpoint.';
ALTER TABLE "apitoken" ALTER COLUMN "tenant_id" DROP NOT NULL;
ALTER TABLE "apitoken" ADD "origin" VARCHAR(16) NOT NULL DEFAULT 'pat';
ALTER TABLE "apitoken" ADD "oauth_client_id" INT REFERENCES "mcpoauthclient" ("id") ON DELETE CASCADE;
ALTER TABLE "apitoken" ADD "refresh_token_hash" VARCHAR(64) UNIQUE;
ALTER TABLE "apitoken" ADD "refresh_expires_at" TIMESTAMPTZ;
ALTER TABLE "apitoken" ADD "scope" VARCHAR(255);
CREATE INDEX IF NOT EXISTS "idx_apitoken_origin_a98cdb" ON "apitoken" ("origin");
CREATE INDEX IF NOT EXISTS "idx_apitoken_refresh_fa5b1f" ON "apitoken" ("refresh_token_hash");
COMMENT ON TABLE "apitoken" IS 'A bearer credential acting as its owning user.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_apitoken_refresh_fa5b1f";
DROP INDEX IF EXISTS "idx_apitoken_origin_a98cdb";
ALTER TABLE "apitoken" DROP COLUMN "scope";
ALTER TABLE "apitoken" DROP COLUMN "refresh_expires_at";
ALTER TABLE "apitoken" DROP COLUMN "refresh_token_hash";
ALTER TABLE "apitoken" DROP COLUMN "oauth_client_id";
ALTER TABLE "apitoken" DROP COLUMN "origin";
DELETE FROM "apitoken" WHERE "tenant_id" IS NULL;
ALTER TABLE "apitoken" ALTER COLUMN "tenant_id" SET NOT NULL;
DROP TABLE IF EXISTS "mcpauthorizationcode";
DROP TABLE IF EXISTS "mcpoauthclient";"""
