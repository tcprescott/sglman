"""Store the Challonge organization subdomain a linked tournament lives under.

Challonge v2.1 resolves ``<community>.challonge.com/<slug>`` tournaments only
under ``/communities/<community>/``; the v1-style ``<community>-<slug>``
identifier the link flow used to build 404s. Hand-written and idempotent.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "challonge_community" VARCHAR(64);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "challonge_community";"""
