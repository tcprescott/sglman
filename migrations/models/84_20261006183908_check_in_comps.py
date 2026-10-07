from tortoise import BaseDBAsyncClient

# Check-in comps: per-event comp rules and each entrant's comp reasons.
# Hand-edited from aerich's output, which added comp_roles NOT NULL with no
# default and so fails on any existing event; existing events get no comps.


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "checkinentrant" ADD "comp_reasons" JSONB;
        COMMENT ON COLUMN "checkinentrant"."link_method" IS 'MATCHERINO_ID: matcherino_id
DISCORD_ID: discord_id
TWITCH_ID: twitch_id
MATCHERINO_HANDLE: matcherino_handle
MANUAL: manual
WALK_UP: walk_up
COMP: comp';
        COMMENT ON COLUMN "checkinentrant"."source" IS 'MATCHERINO: matcherino
WALK_UP: walk_up
COMP: comp';
        ALTER TABLE "checkinevent" ADD "comp_volunteers" BOOL NOT NULL DEFAULT False;
        ALTER TABLE "checkinevent" ADD "comp_roles" JSONB NOT NULL DEFAULT '[]'::jsonb;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "checkinevent" DROP COLUMN "comp_volunteers";
        ALTER TABLE "checkinevent" DROP COLUMN "comp_roles";
        ALTER TABLE "checkinentrant" DROP COLUMN "comp_reasons";
        COMMENT ON COLUMN "checkinentrant"."link_method" IS 'MATCHERINO_ID: matcherino_id
DISCORD_ID: discord_id
TWITCH_ID: twitch_id
MATCHERINO_HANDLE: matcherino_handle
MANUAL: manual
WALK_UP: walk_up';
        COMMENT ON COLUMN "checkinentrant"."source" IS 'MATCHERINO: matcherino
WALK_UP: walk_up';"""
