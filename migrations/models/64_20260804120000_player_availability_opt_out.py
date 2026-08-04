from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    # Player availability flipped from opt-in ("the only times I can play") to
    # opt-out ("the times I cannot"). Read under the new meaning, an "available
    # 09:00-13:00" window says the opposite of what its author meant, and an
    # "unavailable" one carved a hole in a declaration that no longer exists.
    # Clearing those two starts everyone from the new default — available for
    # the whole event — instead of silently inverting what they entered.
    #
    # PREFERRED rows survive: "I would rather play then" means the same thing
    # before and after the flip, and it is still the signal the suggestion
    # service ranks by. Volunteer availability is untouched; it stays opt-in.
    return """
        DELETE FROM "playeravailability" WHERE "status" <> 'preferred';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return ""
