from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    # mmr is no longer a randomizer: Majora's Mask is rolled offline. A preset on
    # it can't be saved or rolled any more, and a tournament still naming it
    # would show "rolling seeds with mmr" and fail every roll. Every FK to
    # preset is ON DELETE SET NULL, so the deletes detach rather than cascade.
    # GeneratedSeeds.randomizer is history and keeps its value.
    return """
        DELETE FROM "preset" WHERE "randomizer" = 'mmr';
        UPDATE "tournament" SET "seed_generator" = NULL WHERE "seed_generator" = 'mmr';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    # Data-only; the deleted presets and cleared generators are not recoverable.
    return ""
