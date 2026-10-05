from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "checkinentrant" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "source" VARCHAR(16) NOT NULL,
    "matcherino_user_id" VARCHAR(64),
    "display_name" VARCHAR(255) NOT NULL,
    "avatar_url" VARCHAR(512),
    "auth_provider" VARCHAR(32),
    "auth_id" VARCHAR(128),
    "twitch_login" VARCHAR(255),
    "registered_at" TIMESTAMPTZ,
    "source_data" JSONB,
    "link_method" VARCHAR(24),
    "withdrawn_at" TIMESTAMPTZ,
    "checked_in_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "checked_in_by_id" INT REFERENCES "user" ("id") ON DELETE SET NULL,
    "event_id" INT NOT NULL REFERENCES "checkinevent" ("id") ON DELETE CASCADE,
    "linked_by_id" INT REFERENCES "user" ("id") ON DELETE SET NULL,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    "user_id" INT REFERENCES "user" ("id") ON DELETE SET NULL,
    CONSTRAINT "uid_checkinentr_event_i_2ab6cc" UNIQUE ("event_id", "matcherino_user_id"),
    CONSTRAINT "uid_checkinentr_event_i_a6980a" UNIQUE ("event_id", "user_id")
);
CREATE INDEX IF NOT EXISTS "idx_checkinentr_event_i_90af2c" ON "checkinentrant" ("event_id", "checked_in_at");
COMMENT ON COLUMN "checkinentrant"."source" IS 'MATCHERINO: matcherino\nWALK_UP: walk_up';
COMMENT ON COLUMN "checkinentrant"."link_method" IS 'MATCHERINO_ID: matcherino_id\nDISCORD_ID: discord_id\nTWITCH_ID: twitch_id\nTWITCH_LOGIN: twitch_login\nMATCHERINO_HANDLE: matcherino_handle\nMANUAL: manual\nWALK_UP: walk_up';
COMMENT ON TABLE "checkinentrant" IS 'One person on a check-in event''s roster.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "checkinentrant";"""
