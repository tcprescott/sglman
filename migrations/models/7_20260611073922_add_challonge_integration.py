from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "challongeconnection" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "access_token" VARCHAR(512) NOT NULL,
    "refresh_token" VARCHAR(512),
    "token_expires_at" TIMESTAMPTZ,
    "scopes" VARCHAR(255),
    "challonge_username" VARCHAR(255),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "connected_by_id" INT REFERENCES "user" ("id") ON DELETE SET NULL
);
COMMENT ON TABLE "challongeconnection" IS 'Single shared SGL service-account OAuth connection to Challonge.';
        CREATE TABLE IF NOT EXISTS "challongeparticipant" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "challonge_participant_id" VARCHAR(64) NOT NULL,
    "name" VARCHAR(255),
    "challonge_user_id" VARCHAR(64),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "tournament_id" INT NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE,
    "user_id" INT REFERENCES "user" ("id") ON DELETE SET NULL,
    CONSTRAINT "uid_challongepa_tournam_55c0ae" UNIQUE ("tournament_id", "challonge_participant_id")
);
COMMENT ON TABLE "challongeparticipant" IS 'A Challonge participant in a linked tournament, mirrored into sglman.';
        CREATE TABLE IF NOT EXISTS "challongematch" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "challonge_match_id" VARCHAR(64) NOT NULL,
    "round" INT,
    "state" VARCHAR(20) NOT NULL DEFAULT 'pending',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "match_id" INT REFERENCES "match" ("id") ON DELETE SET NULL,
    "participant1_id" INT REFERENCES "challongeparticipant" ("id") ON DELETE SET NULL,
    "participant2_id" INT REFERENCES "challongeparticipant" ("id") ON DELETE SET NULL,
    "tournament_id" INT NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE,
    "winner_participant_id" INT REFERENCES "challongeparticipant" ("id") ON DELETE SET NULL,
    CONSTRAINT "uid_challongema_tournam_f78016" UNIQUE ("tournament_id", "challonge_match_id")
);
COMMENT ON COLUMN "challongematch"."state" IS 'PENDING: pending\nOPEN: open\nCOMPLETE: complete';
COMMENT ON TABLE "challongematch" IS 'A Challonge bracket match mirrored into sglman.';
        ALTER TABLE "tournament" ADD "challonge_tournament_id" VARCHAR(64);
        ALTER TABLE "tournament" ADD "challonge_tournament_url" VARCHAR(255);
        ALTER TABLE "user" ADD "challonge_username" VARCHAR(255);
        ALTER TABLE "user" ADD "challonge_user_id" VARCHAR(64);
        ALTER TABLE "user" ADD "challonge_linked_at" TIMESTAMPTZ;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "user" DROP COLUMN "challonge_username";
        ALTER TABLE "user" DROP COLUMN "challonge_user_id";
        ALTER TABLE "user" DROP COLUMN "challonge_linked_at";
        ALTER TABLE "tournament" DROP COLUMN "challonge_tournament_id";
        ALTER TABLE "tournament" DROP COLUMN "challonge_tournament_url";
        DROP TABLE IF EXISTS "challongeconnection";
        DROP TABLE IF EXISTS "challongematch";
        DROP TABLE IF EXISTS "challongeparticipant";"""
