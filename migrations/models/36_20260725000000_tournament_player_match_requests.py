from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" ADD "allow_player_match_requests" BOOL NOT NULL DEFAULT True;
        UPDATE "tournament" SET "allow_player_match_requests" = False
        WHERE "challonge_tournament_id" IS NOT NULL
           OR "id" IN (SELECT DISTINCT "tournament_id" FROM "bracket");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" DROP COLUMN "allow_player_match_requests";"""
