from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    """Rename ``streamroom`` → ``stage`` and ``match.stream_room_id`` → ``stage_id``.

    A pure rename: same rows, same FK semantics (still ``SET NULL``), no data
    movement. Postgres carries neither indexes, constraints nor the identity
    sequence along with a renamed table, so each is renamed in its own loop
    rather than being dropped and recreated — dropping the unique index on
    ``(tenant_id, name)`` would leave a window where a duplicate stage name
    could land.

    Renaming a unique/primary-key index renames the constraint that owns it, so
    only foreign keys need the separate ``RENAME CONSTRAINT`` pass.
    """
    return """
        ALTER TABLE "streamroom" RENAME TO "stage";
        ALTER TABLE "match" RENAME COLUMN "stream_room_id" TO "stage_id";
        ALTER SEQUENCE IF EXISTS "streamroom_id_seq" RENAME TO "stage_id_seq";
        DO $$
        DECLARE r record;
        BEGIN
            FOR r IN
                SELECT indexname FROM pg_indexes
                 WHERE schemaname = current_schema()
                   AND (indexname LIKE '%streamroom%' OR indexname LIKE '%stream_room%')
            LOOP
                EXECUTE format(
                    'ALTER INDEX %I RENAME TO %I', r.indexname,
                    replace(replace(r.indexname, 'streamroom', 'stage'), 'stream_room', 'stage')
                );
            END LOOP;
            FOR r IN
                SELECT c.conname, c.conrelid::regclass::text AS tbl
                  FROM pg_constraint c
                 WHERE c.contype = 'f'
                   AND (c.conname LIKE '%streamroom%' OR c.conname LIKE '%stream_room%')
            LOOP
                EXECUTE format(
                    'ALTER TABLE %s RENAME CONSTRAINT %I TO %I', r.tbl, r.conname,
                    replace(replace(r.conname, 'streamroom', 'stage'), 'stream_room', 'stage')
                );
            END LOOP;
        END $$;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    """Reverse of :func:`upgrade`.

    Both loops are constrained to the two affected tables: a bare ``%stage%``
    match would also catch the bracket tables, where ``stage_order`` is an
    unrelated concept that predates this rename.
    """
    return """
        ALTER TABLE "stage" RENAME TO "streamroom";
        ALTER TABLE "match" RENAME COLUMN "stage_id" TO "stream_room_id";
        ALTER SEQUENCE IF EXISTS "stage_id_seq" RENAME TO "streamroom_id_seq";
        DO $$
        DECLARE r record;
        BEGIN
            FOR r IN
                SELECT indexname FROM pg_indexes
                 WHERE schemaname = current_schema()
                   AND tablename IN ('streamroom', 'match')
                   AND indexname LIKE '%stage%'
            LOOP
                EXECUTE format(
                    'ALTER INDEX %I RENAME TO %I', r.indexname,
                    replace(r.indexname, 'stage', 'streamroom')
                );
            END LOOP;
            FOR r IN
                SELECT c.conname, c.conrelid::regclass::text AS tbl
                  FROM pg_constraint c
                 WHERE c.contype = 'f'
                   AND c.conrelid IN ('"streamroom"'::regclass, '"match"'::regclass)
                   AND c.conname LIKE '%stage%'
            LOOP
                EXECUTE format(
                    'ALTER TABLE %s RENAME CONSTRAINT %I TO %I', r.tbl, r.conname,
                    replace(r.conname, 'stage', 'streamroom')
                );
            END LOOP;
        END $$;"""
