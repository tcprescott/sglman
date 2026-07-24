"""Best-of-N series: ``bracketmatchgame`` replaces the one-shot ``bracketmatch.match``.

A bracket match now spans ``best_of`` games and **every game is its own scheduled
``Match``**. That link moves off ``bracketmatch.match_id`` (which could hold only
one) onto a new child table, so a best-of-1 is simply a series with a single game
and there is one code path rather than a special case.

1. ``bracketmatchgame`` — one row per *scheduled* game. ``match_id`` is UNIQUE
   (a ``Match`` backs at most one game) and ``ON DELETE SET NULL``, so deleting a
   Match preserves the recorded result. A game the series never needed ends
   ``cancelled`` rather than being deleted, which keeps ``game_number`` stable and
   records why it was never played.
2. **Backfill** every existing ``bracketmatch.match_id`` into game 1 of its
   series, carrying the tenant and — for an already-decided slot — its winner and
   forfeit flag, so no scheduling history is lost.
3. ``bracketmatch.match_id`` is dropped and ``bracketmatch.best_of`` added (the
   per-matchup override of the round's ``Bracket.config['rounds'][N]['best_of']``,
   which until now was display-only chrome).

Order is load-bearing: create → backfill → drop. Dropping before the backfill
would silently lose every existing link.

Hand-written (like migrations 14/18-31) to keep the numbered chain contiguous and
because the backfill is not something aerich can express. Every statement is
idempotent. The downgrade is inherently lossy for games 2+ — it can only restore
the single game-1 link that the old column was able to hold.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "bracketmatchgame" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "game_number" INT NOT NULL,
            "forfeit" BOOL NOT NULL DEFAULT False,
            "state" VARCHAR(16) NOT NULL DEFAULT 'scheduled',
            "cancelled_reason" VARCHAR(255),
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            "bracket_match_id" INT NOT NULL REFERENCES "bracketmatch" ("id") ON DELETE CASCADE,
            "match_id" INT UNIQUE REFERENCES "match" ("id") ON DELETE SET NULL,
            "winner_entry_id" INT REFERENCES "bracketentry" ("id") ON DELETE SET NULL,
            CONSTRAINT "uid_bracketmat_bracket_game" UNIQUE ("bracket_match_id", "game_number")
        );
        CREATE INDEX IF NOT EXISTS "idx_bracketmatchgame_bracket_match"
            ON "bracketmatchgame" ("bracket_match_id");
        CREATE INDEX IF NOT EXISTS "idx_bracketmatchgame_match"
            ON "bracketmatchgame" ("match_id");

        INSERT INTO "bracketmatchgame" (
            "tenant_id", "bracket_match_id", "game_number", "match_id",
            "winner_entry_id", "forfeit", "state", "created_at", "updated_at"
        )
        SELECT
            "tenant_id",
            "id",
            1,
            "match_id",
            CASE WHEN "state" = 'complete' THEN "winner_id" END,
            CASE WHEN "state" = 'complete' THEN "forfeit" ELSE False END,
            CASE WHEN "state" = 'complete' THEN 'complete' ELSE 'scheduled' END,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM "bracketmatch"
        WHERE "match_id" IS NOT NULL
        ON CONFLICT DO NOTHING;

        ALTER TABLE "bracketmatch" DROP COLUMN IF EXISTS "match_id";
        ALTER TABLE "bracketmatch" ADD COLUMN IF NOT EXISTS "best_of" INT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "bracketmatch" ADD COLUMN IF NOT EXISTS "match_id" INT
            REFERENCES "match" ("id") ON DELETE SET NULL;
        UPDATE "bracketmatch" AS bm
            SET "match_id" = g."match_id"
            FROM "bracketmatchgame" AS g
            WHERE g."bracket_match_id" = bm."id" AND g."game_number" = 1;
        CREATE INDEX IF NOT EXISTS "idx_bracketmatch_match" ON "bracketmatch" ("match_id");
        ALTER TABLE "bracketmatch" DROP COLUMN IF EXISTS "best_of";
        DROP TABLE IF EXISTS "bracketmatchgame";"""
