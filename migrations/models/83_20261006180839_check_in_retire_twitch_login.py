from tortoise import BaseDBAsyncClient

# CheckInLinkMethod.TWITCH_LOGIN matched the Twitch socials on a bounty's
# participant list; venue sales carry none, so nothing produces it any more.
# Rows linked that way become TWITCH_ID: both read "via Twitch" at the desk and
# both are remembered on the account, so nothing a volunteer sees changes.
# The downgrade leaves them as TWITCH_ID, which the old enum also accepts.


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "checkinentrant" SET "link_method" = 'twitch_id' WHERE "link_method" = 'twitch_login';
        COMMENT ON COLUMN "checkinentrant"."link_method" IS 'MATCHERINO_ID: matcherino_id
DISCORD_ID: discord_id
TWITCH_ID: twitch_id
MATCHERINO_HANDLE: matcherino_handle
MANUAL: manual
WALK_UP: walk_up';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        COMMENT ON COLUMN "checkinentrant"."link_method" IS 'MATCHERINO_ID: matcherino_id
DISCORD_ID: discord_id
TWITCH_ID: twitch_id
TWITCH_LOGIN: twitch_login
MATCHERINO_HANDLE: matcherino_handle
MANUAL: manual
WALK_UP: walk_up';"""
