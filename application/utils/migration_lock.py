"""Cross-process mutual exclusion for the schema migration run at startup.

``main.init_db`` calls Aerich's ``upgrade()`` on every boot, and Aerich has no
locking of its own. One replica is the current deployment, but a deploy where
the new container starts before the old one exits — or a crash-loop that
restarts fast — puts two processes into the same migration chain at once. Each
reads the same ``aerich`` version row, each decides the same files are pending,
and both run them. The failure is not a clean error: half-applied DDL and a
version row that disagrees with the schema.

A Postgres advisory lock costs one extra connection held for the length of the
upgrade and removes the race entirely. The lock is session-scoped, so it must be
taken on a connection this module owns for its whole lifetime rather than on one
borrowed from Tortoise's pool, where a second statement can land on a different
connection and unlock nothing.

Non-PostgreSQL DSNs (SQLite, under test) are a no-op: there is no second process
to exclude.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

logger = logging.getLogger('wizzrobe.migrations')

# Arbitrary but fixed: any process that changes this stops excluding the ones
# that did not. Advisory-lock keys share one namespace per database, so the
# value only has to be unlikely to collide with another application's.
MIGRATION_LOCK_KEY = 0x5A11_0B00

# A wait this long means another process is stuck mid-migration, not merely
# slow. Failing startup is the right answer — the alternative is migrating
# alongside it, which is the exact race the lock exists to prevent.
LOCK_TIMEOUT_SECONDS = 300


def _is_postgres(dsn: str) -> bool:
    return dsn.startswith('postgres://') or dsn.startswith('postgresql://')


@asynccontextmanager
async def migration_lock(dsn: str, acquire_timeout: float = LOCK_TIMEOUT_SECONDS) -> AsyncIterator[bool]:
    """Hold the migration advisory lock for the duration of the block.

    Yields ``True`` when a lock was actually taken, ``False`` when the backend
    is not PostgreSQL and the block runs unguarded.

    ``acquire_timeout`` bounds waiting for the lock, never the block itself: the
    block is a migration and takes as long as it takes.

    Raises:
        TimeoutError: another process held the lock past ``acquire_timeout``.
    """
    if not _is_postgres(dsn):
        yield False
        return

    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        try:
            await asyncio.wait_for(
                conn.execute('SELECT pg_advisory_lock($1)', MIGRATION_LOCK_KEY),
                timeout=acquire_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f'Timed out after {acquire_timeout}s waiting for the migration lock. Another process is '
                'likely stuck part-way through a migration; resolve that before restarting.'
            ) from exc
        logger.info('Holding the migration lock (key=%s).', MIGRATION_LOCK_KEY)
        try:
            yield True
        finally:
            await conn.execute('SELECT pg_advisory_unlock($1)', MIGRATION_LOCK_KEY)
            logger.info('Released the migration lock.')
    finally:
        await conn.close()
