from tortoise import BaseDBAsyncClient

# Event check-in moves from a Matcherino bounty's participant list to its
# ticketed venue's badge sales. Hand-written because aerich gets three things
# wrong here: it offers a RENAME of matcherino_bounty_id to matcherino_venue_id
# (a bounty id is not a venue id, so the old values must not carry over), it
# drops the old unique pair with DROP INDEX although it is a table constraint,
# and it creates checkinpass before the checkintier table it references.


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "checkinevent" DROP CONSTRAINT IF EXISTS "uid_checkineven_tenant__02fb71";
        ALTER TABLE "checkinevent" DROP COLUMN IF EXISTS "matcherino_bounty_id";
        ALTER TABLE "checkinevent" ADD "matcherino_venue_id" INT;
        ALTER TABLE "checkinevent" ADD CONSTRAINT "uid_checkineven_tenant__038ab6" UNIQUE ("tenant_id", "matcherino_venue_id");
        ALTER TABLE "checkinentrant" DROP COLUMN IF EXISTS "twitch_login";
        CREATE TABLE IF NOT EXISTS "checkintier" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "matcherino_pass_id" INT NOT NULL,
    "title" VARCHAR(255) NOT NULL,
    "amount_cents" INT NOT NULL DEFAULT 0,
    "role" VARCHAR(32),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "event_id" INT NOT NULL REFERENCES "checkinevent" ("id") ON DELETE CASCADE,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_checkintier_event_i_9f325c" UNIQUE ("event_id", "matcherino_pass_id")
);
COMMENT ON TABLE "checkintier" IS 'A kind of badge sold on the event''s Matcherino venue (Base, VIP, Day Pass).';
        CREATE TABLE IF NOT EXISTS "checkinpass" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "matcherino_purchase_id" INT NOT NULL,
    "buyer_matcherino_user_id" VARCHAR(64) NOT NULL,
    "code" VARCHAR(32) NOT NULL,
    "purchased_at" TIMESTAMPTZ,
    "refunded_at" TIMESTAMPTZ,
    "removed_at" TIMESTAMPTZ,
    "source_data" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "entrant_id" INT REFERENCES "checkinentrant" ("id") ON DELETE SET NULL,
    "event_id" INT NOT NULL REFERENCES "checkinevent" ("id") ON DELETE CASCADE,
    "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
    "tier_id" INT NOT NULL REFERENCES "checkintier" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_checkinpass_event_i_26da27" UNIQUE ("event_id", "matcherino_purchase_id")
);
CREATE INDEX IF NOT EXISTS "idx_checkinpass_event_i_4a58f0" ON "checkinpass" ("event_id", "code");
COMMENT ON TABLE "checkinpass" IS 'One badge bought on the event''s Matcherino venue.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "checkinpass";
        DROP TABLE IF EXISTS "checkintier";
        ALTER TABLE "checkinentrant" ADD "twitch_login" VARCHAR(255);
        ALTER TABLE "checkinevent" DROP CONSTRAINT IF EXISTS "uid_checkineven_tenant__038ab6";
        ALTER TABLE "checkinevent" DROP COLUMN IF EXISTS "matcherino_venue_id";
        ALTER TABLE "checkinevent" ADD "matcherino_bounty_id" INT;
        ALTER TABLE "checkinevent" ADD CONSTRAINT "uid_checkineven_tenant__02fb71" UNIQUE ("tenant_id", "matcherino_bounty_id");"""
