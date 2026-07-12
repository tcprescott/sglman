"""Multitenancy: default-tenant backfill, not a rebuild.

Logical multitenancy lands as an **additive** change so the live single-tenant
deployment's data survives. Three ordered steps, run in one transaction (a
missed table then fails the ``SET NOT NULL`` loudly rather than shipping orphan
NULLs):

1. **Schema-add** — create ``tenant`` + ``tenantmembership``; add a **nullable**
   ``tenant_id`` (+ FK + index) to every scoped table; add each new per-tenant
   composite unique *alongside* the old single-column ones (NULLs are distinct,
   so this is satisfiable before backfill).
2. **Backfill** — insert one default ``Tenant`` (slug ``default``,
   ``discord_guild_id`` copied from the existing ``discord_role_sync_guild_id``
   config so the shared bot's guild→tenant routing matches the live guild after
   cutover); stamp every scoped row — including the ``auditlog`` /
   ``telemetryevent`` / ``userrole`` history — with it; add a
   ``TenantMembership`` for every existing user. Because every row lands in the
   same tenant, FK-safe ordering is moot.
3. **Constraint-tighten** — ``SET NOT NULL`` on the scoped FKs (all except
   ``auditlog`` / ``telemetryevent`` / ``userrole``, nullable by design), then
   drop the now-superseded single-column / old-composite uniques.

Hand-written (like migrations 14/18/19) to keep the numbered chain contiguous.
Dynamic ``pg_constraint`` lookups drop the old uniques by column-set so
auto-generated constraint names don't have to be guessed.

Downgrade is best-effort (drops the tenancy objects, re-adds the old uniques);
once more than one tenant exists it cannot cleanly restore single-tenant
uniqueness — restore from backup for a true rollback.
"""

from tortoise import BaseDBAsyncClient

# Scoped tables gaining a NOT-NULL tenant_id, ON DELETE CASCADE. ``tenantmembership``
# is created below already carrying the column, so it is not in this list.
_SCOPED_CASCADE = [
    'apitoken', 'challongeapiusage', 'challongeconnection', 'challongematch',
    'challongeparticipant', 'commentator', 'discordrolemapping', 'equipment',
    'equipmentloan', 'feedback', 'generatedseeds', 'match', 'matchacknowledgment',
    'matchplayers', 'matchwatcher', 'playeravailability', 'streamroom',
    'systemconfiguration', 'tournament', 'tournamentnotificationpreference',
    'tournamentplayers', 'tracker', 'triforcetext', 'volunteerassignment',
    'volunteeravailability', 'volunteerposition', 'volunteerprofile',
    'volunteerqualification', 'volunteershift', 'webhook', 'webhookdelivery',
]

# Append-only trails: nullable tenant_id, ON DELETE SET NULL (NULL = platform row).
_SCOPED_SETNULL = ['auditlog', 'telemetryevent']

# UserRole: nullable tenant_id (NULL = SUPER_ADMIN), ON DELETE CASCADE.
_SCOPED_NULL_CASCADE = ['userrole']

# All tables whose existing rows get stamped with the default tenant.
_BACKFILL_TABLES = _SCOPED_CASCADE + _SCOPED_SETNULL + _SCOPED_NULL_CASCADE

# New per-tenant unique indexes: (index_name, table, columns_sql).
_NEW_UNIQUES = [
    ('uid_streamroom_tenant_name', 'streamroom', '"tenant_id", "name"'),
    ('uid_syscfg_tenant_name', 'systemconfiguration', '"tenant_id", "name"'),
    ('uid_volpos_tenant_name', 'volunteerposition', '"tenant_id", "name"'),
    ('uid_drm_tenant_role_app', 'discordrolemapping', '"tenant_id", "discord_role_id", "app_role"'),
    ('uid_equipment_tenant_asset', 'equipment', '"tenant_id", "asset_number"'),
    ('uid_challusage_tenant_period', 'challongeapiusage', '"tenant_id", "period"'),
    ('uid_userrole_user_role_tenant', 'userrole', '"user_id", "role", "tenant_id"'),
    ('uid_volprofile_tenant_user', 'volunteerprofile', '"tenant_id", "user_id"'),
]

# Old uniques to drop after backfill: (table, columns) — dropped by column-set so
# auto-named inline uniques and named composites are both handled.
_OLD_UNIQUES = [
    ('streamroom', ('name',)),
    ('systemconfiguration', ('name',)),
    ('volunteerposition', ('name',)),
    ('equipment', ('asset_number',)),
    ('challongeapiusage', ('period',)),
    ('volunteerprofile', ('user_id',)),
    ('userrole', ('user_id', 'role')),
    ('discordrolemapping', ('guild_id', 'discord_role_id', 'app_role')),
]


def _add_tenant_column(table: str, on_delete: str) -> str:
    # Column added nullable; NOT NULL is enforced later (after backfill).
    return (
        f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "tenant_id" INT;\n'
        f'ALTER TABLE "{table}" ADD CONSTRAINT "{table}_tenant_id_fkey" '
        f'FOREIGN KEY ("tenant_id") REFERENCES "tenant" ("id") ON DELETE {on_delete};\n'
        f'CREATE INDEX IF NOT EXISTS "idx_{table}_tenant_id" ON "{table}" ("tenant_id");'
    )


def _drop_unique_on(table: str, columns: tuple[str, ...]) -> str:
    # Compare column sets as text[] (attname is the ``name`` type; cast both sides).
    sorted_cols = ", ".join(f"'{c}'" for c in sorted(columns))
    return f"""
        DO $$
        DECLARE cname text;
        BEGIN
            SELECT c.conname INTO cname
            FROM pg_constraint c
            WHERE c.conrelid = '"{table}"'::regclass AND c.contype = 'u'
              AND (
                SELECT array_agg(a.attname::text ORDER BY a.attname::text)
                FROM unnest(c.conkey) k
                JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k
              ) = ARRAY[{sorted_cols}]::text[]
            LIMIT 1;
            IF cname IS NOT NULL THEN
                EXECUTE format('ALTER TABLE "{table}" DROP CONSTRAINT %I', cname);
            END IF;
        END $$;"""


async def upgrade(db: BaseDBAsyncClient) -> str:
    stmts: list[str] = []

    # --- Step 1: schema-add ------------------------------------------------
    stmts.append("""
        CREATE TABLE IF NOT EXISTS "tenant" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "name" VARCHAR(255) NOT NULL,
            "slug" VARCHAR(64) NOT NULL UNIQUE,
            "domain" VARCHAR(255) UNIQUE,
            "discord_guild_id" BIGINT,
            "is_active" BOOL NOT NULL DEFAULT True,
            "config" JSONB NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS "idx_tenant_slug" ON "tenant" ("slug");
        CREATE INDEX IF NOT EXISTS "idx_tenant_domain" ON "tenant" ("domain");
        CREATE INDEX IF NOT EXISTS "idx_tenant_guild" ON "tenant" ("discord_guild_id");
        COMMENT ON TABLE "tenant" IS 'One independent tournament community on the shared deployment.';""")

    stmts.append("""
        CREATE TABLE IF NOT EXISTS "tenantmembership" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "tenant_id" INT NOT NULL REFERENCES "tenant" ("id") ON DELETE CASCADE,
            "user_id" INT NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
            CONSTRAINT "uid_tenantmembership_user_tenant" UNIQUE ("user_id", "tenant_id")
        );
        CREATE INDEX IF NOT EXISTS "idx_tenantmembership_tenant_id" ON "tenantmembership" ("tenant_id");
        COMMENT ON TABLE "tenantmembership" IS 'Ties a global User to a Tenant they belong to.';""")

    for table in _SCOPED_CASCADE + _SCOPED_NULL_CASCADE:
        stmts.append(_add_tenant_column(table, 'CASCADE'))
    for table in _SCOPED_SETNULL:
        stmts.append(_add_tenant_column(table, 'SET NULL'))

    for name, table, cols in _NEW_UNIQUES:
        stmts.append(f'CREATE UNIQUE INDEX IF NOT EXISTS "{name}" ON "{table}" ({cols});')

    # --- Step 2: backfill --------------------------------------------------
    # Default tenant; discord_guild_id sourced from the existing global config so
    # guild→tenant routing matches the live guild after cutover.
    stmts.append("""
        INSERT INTO "tenant" ("name", "slug", "domain", "discord_guild_id", "is_active", "config")
        SELECT 'Default', 'default', NULL,
               (SELECT NULLIF(value, '')::bigint FROM "systemconfiguration"
                WHERE name = 'discord_role_sync_guild_id' LIMIT 1),
               True, '{}'
        ON CONFLICT ("slug") DO NOTHING;""")

    for table in _BACKFILL_TABLES:
        stmts.append(
            f'UPDATE "{table}" SET "tenant_id" = '
            f'(SELECT id FROM "tenant" WHERE slug = \'default\') '
            f'WHERE "tenant_id" IS NULL;'
        )

    stmts.append("""
        INSERT INTO "tenantmembership" ("tenant_id", "user_id")
        SELECT (SELECT id FROM "tenant" WHERE slug = 'default'), "id" FROM "user"
        ON CONFLICT ("user_id", "tenant_id") DO NOTHING;""")

    # --- Step 3: constraint-tighten ---------------------------------------
    for table in _SCOPED_CASCADE:
        stmts.append(f'ALTER TABLE "{table}" ALTER COLUMN "tenant_id" SET NOT NULL;')

    for table, cols in _OLD_UNIQUES:
        stmts.append(_drop_unique_on(table, cols))

    return "\n".join(stmts)


async def downgrade(db: BaseDBAsyncClient) -> str:
    stmts: list[str] = []
    for name, _table, _cols in _NEW_UNIQUES:
        stmts.append(f'DROP INDEX IF EXISTS "{name}";')
    for table in _BACKFILL_TABLES:
        stmts.append(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS "tenant_id";')
    stmts.append('DROP TABLE IF EXISTS "tenantmembership";')
    stmts.append('DROP TABLE IF EXISTS "tenant";')
    # Best-effort restore of the old uniques (fails if multi-tenant duplicates
    # were introduced — restore from backup for a true rollback in that case).
    stmts += [
        'CREATE UNIQUE INDEX IF NOT EXISTS "streamroom_name_key" ON "streamroom" ("name");',
        'CREATE UNIQUE INDEX IF NOT EXISTS "systemconfiguration_name_key" ON "systemconfiguration" ("name");',
        'CREATE UNIQUE INDEX IF NOT EXISTS "volunteerposition_name_key" ON "volunteerposition" ("name");',
        'CREATE UNIQUE INDEX IF NOT EXISTS "equipment_asset_number_key" ON "equipment" ("asset_number");',
        'CREATE UNIQUE INDEX IF NOT EXISTS "challongeapiusage_period_key" ON "challongeapiusage" ("period");',
        'CREATE UNIQUE INDEX IF NOT EXISTS "volunteerprofile_user_id_key" ON "volunteerprofile" ("user_id");',
        'CREATE UNIQUE INDEX IF NOT EXISTS "uid_userrole_user_id_8e9ce0" ON "userrole" ("user_id", "role");',
        'CREATE UNIQUE INDEX IF NOT EXISTS "uid_discordrole_guild_i_16fbfa" ON "discordrolemapping" ("guild_id", "discord_role_id", "app_role");',
    ]
    return "\n".join(stmts)
