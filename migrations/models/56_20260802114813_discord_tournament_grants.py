from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "discordrolemapping" ADD "tournament_id" INT;
        ALTER TABLE "discordrolemapping" ADD "tournament_grant" VARCHAR(32);
        ALTER TABLE "discordrolemapping" ALTER COLUMN "app_role" DROP NOT NULL;
        CREATE TABLE IF NOT EXISTS "discordtournamentgrant" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "grant" VARCHAR(32) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    "tournament_id" INT NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_discordtour_tournam_f17780" UNIQUE ("tournament_id", "user_id", "grant")
);
COMMENT ON COLUMN "discordrolemapping"."tournament_grant" IS 'TOURNAMENT_ADMIN: tournament_admin\nCREW_COORDINATOR: crew_coordinator';
COMMENT ON COLUMN "discordtournamentgrant"."grant" IS 'TOURNAMENT_ADMIN: tournament_admin\nCREW_COORDINATOR: crew_coordinator';
COMMENT ON TABLE "discordtournamentgrant" IS 'Provenance for a per-tournament grant the guild-role sync made.';
        ALTER TABLE "discordrolemapping" ADD CONSTRAINT "fk_discordr_tourname_91a44875" FOREIGN KEY ("tournament_id") REFERENCES "tournament" ("id") ON DELETE CASCADE;
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_discordrole_tenant__5e85bc" ON "discordrolemapping" ("tenant_id", "discord_role_id", "tournament_grant", "tournament_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "uid_discordrole_tenant__5e85bc";
        ALTER TABLE "discordrolemapping" DROP CONSTRAINT IF EXISTS "fk_discordr_tourname_91a44875";
        ALTER TABLE "discordrolemapping" DROP COLUMN "tournament_id";
        ALTER TABLE "discordrolemapping" DROP COLUMN "tournament_grant";
        ALTER TABLE "discordrolemapping" ALTER COLUMN "app_role" SET NOT NULL;
        DROP TABLE IF EXISTS "discordtournamentgrant";"""
