from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "generatedseeds" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "seed_url" VARCHAR(255) NOT NULL,
    "seed_info" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "streamroom" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL UNIQUE,
    "stream_url" VARCHAR(255),
    "is_active" BOOL NOT NULL DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "systemconfiguration" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL UNIQUE,
    "value" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "testmodel" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "description" TEXT NOT NULL,
    "value" INT NOT NULL,
    "somethingelse" VARCHAR(255) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "tournament" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "description" TEXT,
    "seed_generator" VARCHAR(255),
    "is_active" BOOL NOT NULL DEFAULT True,
    "players_per_match" INT NOT NULL DEFAULT 2,
    "team_size" INT NOT NULL DEFAULT 1,
    "bracket_url" VARCHAR(255),
    "rules_url" VARCHAR(255),
    "tournament_format" VARCHAR(255),
    "average_match_duration" INT,
    "max_match_duration" INT,
    "staff_administered" BOOL NOT NULL DEFAULT False,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "announcement" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "title" VARCHAR(255) NOT NULL,
    "content" TEXT NOT NULL,
    "is_active" BOOL NOT NULL DEFAULT True,
    "important" BOOL NOT NULL DEFAULT False,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "tournament_id" INT REFERENCES "tournament" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "match" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "scheduled_at" TIMESTAMPTZ,
    "seated_at" TIMESTAMPTZ,
    "started_at" TIMESTAMPTZ,
    "finished_at" TIMESTAMPTZ,
    "confirmed_at" TIMESTAMPTZ,
    "comment" TEXT,
    "is_stream_candidate" BOOL NOT NULL DEFAULT False,
    "title" VARCHAR(255),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "generated_seed_id" INT REFERENCES "generatedseeds" ("id") ON DELETE CASCADE,
    "stream_room_id" INT REFERENCES "streamroom" ("id") ON DELETE CASCADE,
    "tournament_id" INT NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "team" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "tournament_id" INT NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "user" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "discord_id" BIGINT NOT NULL UNIQUE,
    "access_token" VARCHAR(255),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "username" VARCHAR(150) NOT NULL,
    "display_name" VARCHAR(150),
    "pronouns" VARCHAR(50),
    "is_active" BOOL NOT NULL DEFAULT True,
    "dm_notifications" BOOL NOT NULL DEFAULT True
);
CREATE TABLE IF NOT EXISTS "auditlog" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "action" VARCHAR(255) NOT NULL,
    "details" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "commentator" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "approved" BOOL NOT NULL DEFAULT False,
    "acknowledged_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "approved_by_id" INT REFERENCES "user" ("id") ON DELETE CASCADE,
    "match_id" INT NOT NULL REFERENCES "match" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "matchacknowledgment" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "acknowledged_at" TIMESTAMPTZ,
    "auto_acknowledged" BOOL NOT NULL DEFAULT False,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "match_id" INT NOT NULL REFERENCES "match" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_matchacknow_match_i_1a7e2c" UNIQUE ("match_id", "user_id")
);
CREATE TABLE IF NOT EXISTS "matchplayers" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "finish_rank" INT,
    "assigned_station" VARCHAR(50),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "match_id" INT NOT NULL REFERENCES "match" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "matchwatcher" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "match_id" INT NOT NULL REFERENCES "match" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_matchwatche_user_id_c8b82c" UNIQUE ("user_id", "match_id")
);
CREATE TABLE IF NOT EXISTS "tournamentnotificationpreference" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "match_notifications" VARCHAR(30) NOT NULL DEFAULT 'none',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "tournament_id" INT NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_tournamentn_user_id_0ef3bc" UNIQUE ("user_id", "tournament_id")
);
COMMENT ON COLUMN "tournamentnotificationpreference"."match_notifications" IS 'NONE: none\nSTREAMED: streamed\nSTREAMED_AND_CANDIDATES: streamed_and_candidates\nALL: all';
CREATE TABLE IF NOT EXISTS "tournamentplayers" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "tournament_id" INT NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "tracker" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "approved" BOOL NOT NULL DEFAULT False,
    "acknowledged_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "approved_by_id" INT REFERENCES "user" ("id") ON DELETE CASCADE,
    "match_id" INT NOT NULL REFERENCES "match" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "triforcetext" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "text" VARCHAR(200) NOT NULL,
    "author" VARCHAR(200),
    "approved" BOOL,
    "approved_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "approved_by_id" INT REFERENCES "user" ("id") ON DELETE SET NULL,
    "tournament_id" INT NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE,
    "user_id" INT REFERENCES "user" ("id") ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS "userrole" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "role" VARCHAR(32) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "granted_by_id" INT REFERENCES "user" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_userrole_user_id_8e9ce0" UNIQUE ("user_id", "role")
);
COMMENT ON COLUMN "userrole"."role" IS 'STAFF: staff\nPROCTOR: proctor\nSTREAM_MANAGER: stream_manager';
CREATE TABLE IF NOT EXISTS "userteams" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "team_id" INT NOT NULL REFERENCES "team" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS "TournamentCrewCoordinators" (
    "tournament_id" INT NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "uidx_TournamentC_tournam_21c0c3" ON "TournamentCrewCoordinators" ("tournament_id", "user_id");
CREATE TABLE IF NOT EXISTS "TournamentAdmins" (
    "tournament_id" INT NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE,
    "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "uidx_TournamentA_tournam_ede4d6" ON "TournamentAdmins" ("tournament_id", "user_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
