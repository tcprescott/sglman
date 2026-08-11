"""Clear the score left behind on qualifier runs that no longer count.

``review_run`` used to flip a run to REJECTED and then recompute par over the
*approved* set — which the run had just left — so it was never rescored and kept
the score it held while approved. ``_void_run`` had the same shape for a
reattempt. Both now clear the score at the moment the run leaves the set; this
backfills the rows written before that.

Safe by construction: the leaderboard already filters both kinds out, so no total
moves. What changes is what a runner reads on their own runs table (a rejection
beside a score) and what the REST and MCP run payloads report.

The downgrade is deliberately a no-op — the pre-fix values are not recoverable,
and re-deriving them would mean re-scoring runs that should not score.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "asyncqualifierrun" SET "score" = NULL
         WHERE "score" IS NOT NULL
           AND ("reattempted" = true OR "review_status" = 'rejected');"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        -- No-op: the cleared values were stale by definition and are not recoverable.
        SELECT 1;"""
