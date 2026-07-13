"""User-managed presets (PR 1): ``preset`` table + ``tournament.preset`` FK.

Two additive, idempotent changes:

1. A tenant-scoped ``preset`` table (name, randomizer, settings JSON, description)
   with a composite ``unique (tenant_id, randomizer, name)`` — the formerly-global
   preset names namespaced per tenant.
2. ``tournament.preset_id`` — nullable FK, ``ON DELETE SET NULL`` so deleting a
   preset detaches its tournaments rather than removing them. Coexists with the
   legacy ``tournament.seed_generator`` string (FK wins when set).

Hand-written (like migrations 14/18-21) to keep the numbered chain contiguous;
every statement is idempotent.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "preset" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "name" VARCHAR(255) NOT NULL,
            "randomizer" VARCHAR(32) NOT NULL,
            "settings" JSONB NOT NULL,
            "description" TEXT,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            CONSTRAINT "uid_preset_tenant_rand_name" UNIQUE ("tenant_id", "randomizer", "name")
        );
        CREATE INDEX IF NOT EXISTS "idx_preset_tenant_id" ON "preset" ("tenant_id");
        ALTER TABLE "tournament" ADD COLUMN IF NOT EXISTS "preset_id" INT;
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_tournamen_preset_preset_fk'
            ) THEN
                ALTER TABLE "tournament"
                    ADD CONSTRAINT "fk_tournamen_preset_preset_fk"
                    FOREIGN KEY ("preset_id") REFERENCES "preset" ("id") ON DELETE SET NULL;
            END IF;
        END$$;
        CREATE INDEX IF NOT EXISTS "idx_tournament_preset_id" ON "tournament" ("preset_id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "tournament" DROP CONSTRAINT IF EXISTS "fk_tournamen_preset_preset_fk";
        ALTER TABLE "tournament" DROP COLUMN IF EXISTS "preset_id";
        DROP TABLE IF EXISTS "preset";"""
