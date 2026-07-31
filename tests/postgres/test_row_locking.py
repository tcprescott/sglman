"""Concurrency guarantees the SQLite suite structurally cannot prove.

`AsyncQualifierRepository.lock_user_for_draw` takes ``SELECT … FOR UPDATE`` on
the player's row so two simultaneous draw clicks serialize instead of both
passing the "no active run" check and opening two runs. Its own docstring says
the lock "is a harmless no-op on SQLite" — which is exactly why the rest of the
suite can never exercise it. Every other test asserting one-run-at-a-time calls
``start_run`` twice in sequence, where a plain read would pass just as well.

Run with a real PostgreSQL:

    WIZZROBE_TEST_DB_URL=postgres://user:pass@localhost:5432/db \\
        poetry run pytest tests/postgres -q

Without it these skip. The `postgres` CI job supplies the service.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from application.services.async_qualifier.async_qualifier_service import AsyncQualifierService
from models import AsyncQualifierRun, Role, User, UserRole
from tests.conftest import ON_POSTGRES

pytestmark = pytest.mark.skipif(
    not ON_POSTGRES,
    reason="row locking is a no-op on SQLite; set WIZZROBE_TEST_DB_URL to a postgres:// URL",
)


async def _open_qualifier(service, staff, *, runs_per_pool=3):
    now = datetime.now(timezone.utc)
    qualifier = await service.create_qualifier(
        staff, name='Q', opens_at=now - timedelta(days=1), closes_at=now + timedelta(days=1),
        runs_per_pool=runs_per_pool,
    )
    pool = await service.create_pool(staff, qualifier.id, name='Pool A')
    return qualifier, pool


async def test_concurrent_draws_for_one_player_open_exactly_one_run(db):
    """Two clicks landing at once must not both get past the active-run check.

    Without ``FOR UPDATE`` both transactions read "no active run" before either
    inserts, and the player ends up holding two permalinks — one of which they
    never have to play, which is the whole point of a qualifier draw.
    """
    service = AsyncQualifierService()
    staff = await User.create(discord_id=900_101, username='staffy')
    await UserRole.create(user=staff, role=Role.STAFF, tenant_id=1)
    qualifier, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1', 'u2', 'u3'])
    player = await User.create(discord_id=900_102, username='racer')

    results = await asyncio.gather(
        service.start_run(player, qualifier.id, pool.id),
        service.start_run(player, qualifier.id, pool.id),
        return_exceptions=True,
    )

    opened = [r for r in results if isinstance(r, AsyncQualifierRun)]
    refused = [r for r in results if isinstance(r, ValueError)]

    assert len(opened) == 1, (
        f"{len(opened)} concurrent draws opened a run; exactly one should win. "
        f"Results: {results}"
    )
    assert len(refused) == 1 and 'in progress' in str(refused[0])
    assert await AsyncQualifierRun.filter(user_id=player.id).count() == 1


async def test_concurrent_draws_for_different_players_both_succeed(db):
    """The lock is per player — it must not serialize the whole qualifier.

    Locking something coarser (the pool, the qualifier) would also make the test
    above pass while turning every draw in a live qualifier into a queue.
    """
    service = AsyncQualifierService()
    staff = await User.create(discord_id=900_201, username='staffy')
    await UserRole.create(user=staff, role=Role.STAFF, tenant_id=1)
    qualifier, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1', 'u2', 'u3', 'u4'])
    one = await User.create(discord_id=900_202, username='racer1')
    two = await User.create(discord_id=900_203, username='racer2')

    results = await asyncio.gather(
        service.start_run(one, qualifier.id, pool.id),
        service.start_run(two, qualifier.id, pool.id),
        return_exceptions=True,
    )

    assert all(isinstance(r, AsyncQualifierRun) for r in results), (
        f"draws by different players contended with each other: {results}"
    )
    assert {r.user_id for r in results} == {one.id, two.id}
