from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "bracket" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "format" VARCHAR(32) NOT NULL,
    "state" VARCHAR(16) NOT NULL DEFAULT 'draft',
    "stage_order" INT NOT NULL DEFAULT 0,
    "config" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    "tournament_id" INT NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_bracket_tournam_002b27" UNIQUE ("tournament_id", "stage_order")
);
CREATE INDEX IF NOT EXISTS "idx_bracket_tournam_b853b7" ON "bracket" ("tournament_id");
COMMENT ON COLUMN "bracket"."format" IS 'SINGLE_ELIM: single_elim\nDOUBLE_ELIM: double_elim\nSWISS: swiss\nROUND_ROBIN: round_robin';
COMMENT ON COLUMN "bracket"."state" IS 'DRAFT: draft\nACTIVE: active\nCOMPLETE: complete';
COMMENT ON TABLE "bracket" IS 'One stage of a tournament''s bracket.';
        CREATE TABLE IF NOT EXISTS "bracketentrant" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "display_name" VARCHAR(255) NOT NULL,
    "status" VARCHAR(16) NOT NULL DEFAULT 'active',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    "tournament_id" INT NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE,
    "user_id" INT REFERENCES "user" ("id") ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS "idx_bracketentr_tournam_fbfa95" ON "bracketentrant" ("tournament_id");
CREATE INDEX IF NOT EXISTS "idx_bracketentr_user_id_247057" ON "bracketentrant" ("user_id");
COMMENT ON COLUMN "bracketentrant"."status" IS 'ACTIVE: active\nDROPPED: dropped';
COMMENT ON TABLE "bracketentrant" IS 'Tournament-level roster row carrying identity across stages.';
        CREATE TABLE IF NOT EXISTS "bracketentry" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "seed" INT,
    "group_number" INT,
    "final_rank" INT,
    "status" VARCHAR(16) NOT NULL DEFAULT 'active',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "bracket_id" INT NOT NULL REFERENCES "bracket" ("id") ON DELETE CASCADE,
    "entrant_id" INT NOT NULL REFERENCES "bracketentrant" ("id") ON DELETE CASCADE,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_bracketentr_bracket_8a7c98" UNIQUE ("bracket_id", "entrant_id")
);
CREATE INDEX IF NOT EXISTS "idx_bracketentr_bracket_221b08" ON "bracketentry" ("bracket_id");
COMMENT ON COLUMN "bracketentry"."status" IS 'ACTIVE: active\nDROPPED: dropped\nELIMINATED: eliminated';
COMMENT ON TABLE "bracketentry" IS 'An entrant''s participation in one stage.';
        CREATE TABLE IF NOT EXISTS "bracketmatch" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "round" INT NOT NULL,
    "position" INT NOT NULL,
    "group_number" INT,
    "state" VARCHAR(16) NOT NULL DEFAULT 'pending',
    "winner_to_slot" INT,
    "loser_to_slot" INT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "bracket_id" INT NOT NULL REFERENCES "bracket" ("id") ON DELETE CASCADE,
    "entry1_id" INT REFERENCES "bracketentry" ("id") ON DELETE SET NULL,
    "entry2_id" INT REFERENCES "bracketentry" ("id") ON DELETE SET NULL,
    "loser_to_id" INT REFERENCES "bracketmatch" ("id") ON DELETE SET NULL,
    "match_id" INT REFERENCES "match" ("id") ON DELETE SET NULL,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    "winner_id" INT REFERENCES "bracketentry" ("id") ON DELETE SET NULL,
    "winner_to_id" INT REFERENCES "bracketmatch" ("id") ON DELETE SET NULL,
    CONSTRAINT "uid_bracketmatc_bracket_b15b03" UNIQUE ("bracket_id", "round", "position")
);
CREATE INDEX IF NOT EXISTS "idx_bracketmatc_bracket_1c4e9a" ON "bracketmatch" ("bracket_id");
CREATE INDEX IF NOT EXISTS "idx_bracketmatc_match_i_ad442f" ON "bracketmatch" ("match_id");
COMMENT ON COLUMN "bracketmatch"."state" IS 'PENDING: pending\nOPEN: open\nCOMPLETE: complete';
COMMENT ON TABLE "bracketmatch" IS 'One slot in a bracket stage''s persisted match graph.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    # Drop children before the parents they FK-reference (no CASCADE on the
    # tables): bracketmatch → bracketentry/bracket, bracketentry → bracketentrant/
    # bracket, bracketentrant → bracket. Reverse of the create order.
    return """
        DROP TABLE IF EXISTS "bracketmatch";
        DROP TABLE IF EXISTS "bracketentry";
        DROP TABLE IF EXISTS "bracketentrant";
        DROP TABLE IF EXISTS "bracket";"""
