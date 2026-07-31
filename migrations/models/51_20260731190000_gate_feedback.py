"""Gate in-app feedback behind ``FeatureFlag.FEEDBACK``.

Feedback is already in live use, so this backfills the flag as available+enabled
for every existing tenant — gating it must not make a community's feedback form
and review queue vanish out from under them. Same shape as migration 30's
backfill of the four flags that were established when flags were introduced;
``application.feature_flags.established_flags()`` now includes this one.

A tenant created *after* this migration takes the flag from its feature group
like any other (dev's 'Full Access' tier lists every flag), so there is nothing
to seed per tenant.

Hand-written to keep the numbered chain contiguous; the statement is idempotent.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        INSERT INTO "tenantfeatureflag" ("tenant_id", "flag", "available", "enabled")
            SELECT "tenant"."id", 'feedback', True, True
            FROM "tenant"
            ON CONFLICT ("tenant_id", "flag") DO NOTHING;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DELETE FROM "tenantfeatureflag" WHERE "flag" = 'feedback';"""
