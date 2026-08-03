from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    # The preset now decides the randomizer, and TournamentService writes
    # seed_generator from it on every save. Backfill the tournaments linked to a
    # preset before this change: they carry a NULL generator, which is what the
    # schedule's roll button and the triforce-text gate still read.
    return """
        UPDATE "tournament" AS t
        SET "seed_generator" = p."randomizer"
        FROM "preset" AS p
        WHERE t."preset_id" = p."id"
          AND (t."seed_generator" IS NULL OR t."seed_generator" <> p."randomizer");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    # Data-only; the pre-backfill NULLs are not recoverable and re-clearing them
    # would take seed rolling away from tournaments that work.
    return ""
