from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    """Add the per-user timezone preference and pin every existing community.

    Existing communities are pinned to America/New_York — the zone the app
    hardcoded until now — so behaviour is unchanged on deploy and going dynamic
    is a deliberate admin action. Communities created after this migration get
    the ``user`` default from ``TimezoneService.DEFAULT_MODE`` instead.

    ``jsonb_exists`` rather than the ``?`` operator: ``?`` collides with driver
    parameter placeholders in raw SQL.
    """
    return """
        ALTER TABLE "user" ADD "timezone" VARCHAR(64);
        UPDATE "tenant"
           SET "config" = jsonb_set(
                   COALESCE("config", '{}'::jsonb),
                   '{timezone}',
                   '{"mode": "pinned", "name": "America/New_York"}'::jsonb,
                   true
               )
         WHERE NOT jsonb_exists(COALESCE("config", '{}'::jsonb), 'timezone');"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "user" DROP COLUMN "timezone";
        UPDATE "tenant" SET "config" = COALESCE("config", '{}'::jsonb) - 'timezone';"""
