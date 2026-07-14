"""Racetime room lifecycle (PR 6): ``matchplayers.finish_time``.

Additive, idempotent. Adds a nullable finish-time column (whole seconds) to
``matchplayers`` so a racetime room result can record each entrant's elapsed
time alongside the existing ``finish_rank`` (place). Null for non-finishers and
for matches not run through a race room.

Hand-written (like migrations 14/18-24) to keep the numbered chain contiguous.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "matchplayers" ADD COLUMN IF NOT EXISTS "finish_time" INT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "matchplayers" DROP COLUMN IF EXISTS "finish_time";"""
