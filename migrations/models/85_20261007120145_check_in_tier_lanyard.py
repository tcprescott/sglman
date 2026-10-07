from tortoise import BaseDBAsyncClient

# The lanyard each Matcherino badge type earns at the check-in desk. Badge
# types synced before this get the same guess the sync makes for new ones
# (check_in_sales.guess_lanyard): VIP in the title, then Day, else Base.


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "checkintier" ADD "lanyard" VARCHAR(16) NOT NULL DEFAULT 'base';
        UPDATE "checkintier" SET "lanyard" = 'vip' WHERE "title" ILIKE '%vip%';
        UPDATE "checkintier" SET "lanyard" = 'day_pass' WHERE "title" ILIKE '%day%' AND "title" NOT ILIKE '%vip%';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "checkintier" DROP COLUMN "lanyard";"""
