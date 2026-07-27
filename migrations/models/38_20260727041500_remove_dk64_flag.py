from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    """Retire the ``dk64_randomizer`` flag: dk64r is now gated by a per-tenant key.

    Only the per-tenant override rows are removed. ``featureflaggroup.flags`` may
    still list the key; ``FeatureFlagGroup`` documents that unknown keys are
    ignored, and ``FeatureFlagService._clean_flags`` strips it on the next write.
    """
    return """
        DELETE FROM "tenantfeatureflag" WHERE "flag" = 'dk64_randomizer';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    # The deleted overrides carried the community's own on/off choice; there is
    # nothing to restore them from.
    return ""
