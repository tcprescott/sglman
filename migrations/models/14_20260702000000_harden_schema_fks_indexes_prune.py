"""Harden the pre-volunteer schema.

Hand-written because it alters existing constraints and prunes tables rather
than adding columns (aerich's autogen cannot express FK on_delete changes,
dedupe-before-unique, or the dynamic constraint drop, and its snapshot in this
repo has drifted). Validated by applying it to a Postgres built from
migrations 0-13.

1. Replace unintended ``ON DELETE CASCADE`` defaults on detach/attribution FKs
   with ``SET NULL`` (and ``RESTRICT`` on equipment lending history), so
   deleting a stream room / seed / user no longer destroys matches, audit
   history, role grants, crew signups, or loan records.
2. Add duplicate-preventing unique constraints and hot-path indexes the newer
   models already carry but the older ones lack.
3. Drop dead scaffold tables (testmodel, team, userteams, announcement).

The FK swaps look the existing constraint up dynamically (pg_constraint), so
they are safe regardless of how it was originally named.
"""

from tortoise import BaseDBAsyncClient


# (table, column, referenced_table, on_delete)
_FK_CHANGES = [
    ("match", "stream_room_id", "streamroom", "SET NULL"),
    ("match", "generated_seed_id", "generatedseeds", "SET NULL"),
    ("userrole", "granted_by_id", "user", "SET NULL"),
    ("commentator", "approved_by_id", "user", "SET NULL"),
    ("tracker", "approved_by_id", "user", "SET NULL"),
    ("equipmentloan", "checked_in_by_id", "user", "SET NULL"),
    ("equipmentloan", "borrower_id", "user", "RESTRICT"),
    ("equipmentloan", "checked_out_by_id", "user", "RESTRICT"),
    ("auditlog", "user_id", "user", "SET NULL"),
]

# (table, columns) — duplicate rows collapsed (keep lowest id) before unique.
_UNIQUE_JUNCTIONS = [
    ("matchplayers", ("match_id", "user_id")),
    ("tournamentplayers", ("tournament_id", "user_id")),
    ("commentator", ("match_id", "user_id")),
    ("tracker", ("match_id", "user_id")),
]


def _swap_fk(table: str, column: str, ref_table: str, on_delete: str) -> str:
    return f"""
        DO $$
        DECLARE cname text;
        BEGIN
            SELECT c.conname INTO cname
            FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
            WHERE c.conrelid = '"{table}"'::regclass AND c.contype = 'f' AND a.attname = '{column}';
            IF cname IS NOT NULL THEN
                EXECUTE format('ALTER TABLE "{table}" DROP CONSTRAINT %I', cname);
            END IF;
            ALTER TABLE "{table}" ADD CONSTRAINT "{table}_{column}_fkey"
                FOREIGN KEY ("{column}") REFERENCES "{ref_table}" ("id") ON DELETE {on_delete};
        END $$;"""


def _dedupe(table: str, columns: tuple[str, ...]) -> str:
    cols = ", ".join(f'"{c}"' for c in columns)
    match = " AND ".join(f'a."{c}" = b."{c}"' for c in columns)
    return f"""
        DELETE FROM "{table}" a USING "{table}" b WHERE a.id > b.id AND {match};
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_{table}_natkey" ON "{table}" ({cols});"""


async def upgrade(db: BaseDBAsyncClient) -> str:
    statements: list[str] = [
        # AuditLog.user must be nullable before its FK can SET NULL.
        'ALTER TABLE "auditlog" ALTER COLUMN "user_id" DROP NOT NULL;'
    ]

    for table, column, ref_table, on_delete in _FK_CHANGES:
        statements.append(_swap_fk(table, column, ref_table, on_delete))

    # Collapse any duplicate challonge_user_id links (keep earliest); NULLs are
    # unaffected and remain unconstrained.
    statements.append(
        """
        UPDATE "user" SET "challonge_user_id" = NULL
        WHERE "id" IN (
            SELECT a.id FROM "user" a JOIN "user" b
            ON a."challonge_user_id" = b."challonge_user_id" AND a.id > b.id
            WHERE a."challonge_user_id" IS NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS "uid_user_challonge_user_id"
            ON "user" ("challonge_user_id");"""
    )

    for table, columns in _UNIQUE_JUNCTIONS:
        statements.append(_dedupe(table, columns))

    statements.append(
        """
        CREATE INDEX IF NOT EXISTS "idx_match_scheduled_at" ON "match" ("scheduled_at");
        CREATE INDEX IF NOT EXISTS "idx_match_finished_at" ON "match" ("finished_at");
        CREATE INDEX IF NOT EXISTS "idx_auditlog_created_at" ON "auditlog" ("created_at");
        CREATE INDEX IF NOT EXISTS "idx_auditlog_user_id" ON "auditlog" ("user_id");"""
    )

    # Drop dead scaffold tables (userteams references team, so it goes first).
    statements.append(
        """
        DROP TABLE IF EXISTS "userteams" CASCADE;
        DROP TABLE IF EXISTS "team" CASCADE;
        DROP TABLE IF EXISTS "announcement" CASCADE;
        DROP TABLE IF EXISTS "testmodel" CASCADE;"""
    )

    return "\n".join(statements)


async def downgrade(db: BaseDBAsyncClient) -> str:
    # Reverts the reversible changes (FK rules back to CASCADE, drop the added
    # indexes/unique constraints). Dropped scaffold tables are not recreated —
    # restore from git if ever needed.
    statements: list[str] = [
        _swap_fk(table, column, ref_table, "CASCADE")
        for table, column, ref_table, _ in _FK_CHANGES
    ]
    statements.append('ALTER TABLE "auditlog" ALTER COLUMN "user_id" SET NOT NULL;')
    statements.append(
        """
        DROP INDEX IF EXISTS "uid_user_challonge_user_id";
        DROP INDEX IF EXISTS "uid_matchplayers_natkey";
        DROP INDEX IF EXISTS "uid_tournamentplayers_natkey";
        DROP INDEX IF EXISTS "uid_commentator_natkey";
        DROP INDEX IF EXISTS "uid_tracker_natkey";
        DROP INDEX IF EXISTS "idx_match_scheduled_at";
        DROP INDEX IF EXISTS "idx_match_finished_at";
        DROP INDEX IF EXISTS "idx_auditlog_created_at";
        DROP INDEX IF EXISTS "idx_auditlog_user_id";"""
    )
    return "\n".join(statements)
