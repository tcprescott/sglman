from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "volunteerposition" ADD "stagger_minutes" INT;
        ALTER TABLE "volunteerposition" ADD "shift_length_minutes" INT;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "volunteerposition" DROP COLUMN "stagger_minutes";
        ALTER TABLE "volunteerposition" DROP COLUMN "shift_length_minutes";"""
