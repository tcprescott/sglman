"""Record every existing qualifier's window state, so nothing is announced twice.

``window_state_notified`` (migration 70) is what makes an opening or a closing
reach a webhook subscriber exactly once. Left NULL on rows that already exist, the
first worker tick after this deploy reads every currently-open qualifier as *newly*
open and announces it — for something that happened weeks ago.

The CASE below is the SQL of
:func:`application.services.async_qualifier.async_qualifier_rules.window_state`,
evaluated once at deploy time, so the first tick has nothing to report and the next
real crossing is the first thing subscribers hear.

The downgrade clears the stamps, which is what migration 70's own downgrade does by
dropping the column.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "asyncqualifier" SET "window_state_notified" = CASE
            WHEN NOT "is_active" THEN 'closed'
            WHEN "opens_at" IS NOT NULL AND "opens_at" > NOW() THEN 'pending'
            WHEN "closes_at" IS NOT NULL AND "closes_at" <= NOW() THEN 'closed'
            ELSE 'open'
        END
         WHERE "window_state_notified" IS NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "asyncqualifier" SET "window_state_notified" = NULL;"""
