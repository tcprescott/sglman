"""Service tests for AsyncQualifierService: draw, run lifecycle, review, scoring, lockdown."""

from datetime import datetime, timedelta, timezone

import pytest

from application.events import EventType, event_bus
from application.services.async_qualifier_service import AsyncQualifierService
from models import (
    AsyncQualifierPermalink,
    AsyncQualifierRunStatus,
    Role,
    User,
    UserRole,
)

pytestmark = pytest.mark.anyio


async def _staff() -> User:
    u = await User.create(discord_id=900001, username='staffy')
    await UserRole.create(user=u, role=Role.STAFF, tenant_id=1)
    return u


async def _player(discord_id: int, name: str) -> User:
    return await User.create(discord_id=discord_id, username=name)


async def _open_qualifier(service, staff, *, runs_per_pool=1, allowed_reattempts=0):
    now = datetime.now(timezone.utc)
    q = await service.create_qualifier(
        staff, name='Q', opens_at=now - timedelta(days=1), closes_at=now + timedelta(days=1),
        runs_per_pool=runs_per_pool, allowed_reattempts=allowed_reattempts,
    )
    pool = await service.create_pool(staff, q.id, name='Pool A')
    return q, pool


async def test_create_validates(db):
    service = AsyncQualifierService()
    staff = await _staff()
    with pytest.raises(ValueError):
        await service.create_qualifier(staff, name='  ')
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        await service.create_qualifier(staff, name='bad', opens_at=now, closes_at=now - timedelta(hours=1))


async def test_non_admin_cannot_manage(db):
    service = AsyncQualifierService()
    player = await _player(900010, 'p')
    with pytest.raises(PermissionError):
        await service.create_qualifier(player, name='nope')


async def test_draw_reveals_permalink_and_blocks_second_active(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1', 'u2'])
    player = await _player(900011, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    assert run.status == AsyncQualifierRunStatus.IN_PROGRESS
    assert run.permalink is not None and run.permalink.url in {'u1', 'u2'}

    # Second concurrent draw blocked while one is active.
    with pytest.raises(ValueError):
        await service.start_run(player, q.id, pool.id)


async def test_no_repeat_and_runs_per_pool_cap(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff, runs_per_pool=1)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1', 'u2'])
    player = await _player(900012, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    await service.submit_run(player, run.id, elapsed_seconds=1000)
    # runs_per_pool=1 → no more runs allowed in this pool
    with pytest.raises(ValueError):
        await service.start_run(player, q.id, pool.id)


async def test_no_repeat_permalink_across_runs(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff, runs_per_pool=3)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1', 'u2'])
    player = await _player(900013, 'p1')

    seen = set()
    for _ in range(2):
        run = await service.start_run(player, q.id, pool.id)
        seen.add(run.permalink.url)
        await service.submit_run(player, run.id, elapsed_seconds=1000)
    assert seen == {'u1', 'u2'}          # both distinct permalinks drawn
    # pool exhausted (2 permalinks, both played)
    with pytest.raises(ValueError):
        await service.start_run(player, q.id, pool.id)


async def test_submit_then_review_scores_and_sets_par(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    player = await _player(900014, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    await service.submit_run(player, run.id, elapsed_seconds=1200)
    reviewed = await service.review_run(staff, run.id, approved=True, note='looks good')

    assert reviewed.review_status.value == 'approved'
    assert reviewed.score == 100.0  # sole approved run → par == its own time
    permalink = await AsyncQualifierPermalink.get(id=run.permalink_id)
    assert permalink.par_time == 1200


async def test_self_review_blocked(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    # staff is also the runner and a qualifier admin → self-review must be blocked
    await service.add_admin(staff, q.id, staff)
    run = await service.start_run(staff, q.id, pool.id)
    await service.submit_run(staff, run.id, elapsed_seconds=1200)
    with pytest.raises(ValueError):
        await service.review_run(staff, run.id, approved=True)


async def test_forfeit_is_terminal_and_scores_zero(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    player = await _player(900015, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    forfeited = await service.forfeit_run(player, run.id)
    assert forfeited.status == AsyncQualifierRunStatus.FORFEIT
    assert forfeited.score == 0.0
    # can't submit a forfeited run
    with pytest.raises(ValueError):
        await service.submit_run(player, run.id, elapsed_seconds=1000)


async def test_reattempt_requires_reason_and_is_limited(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff, runs_per_pool=1, allowed_reattempts=1)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1', 'u2'])
    player = await _player(900016, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    await service.forfeit_run(player, run.id)

    with pytest.raises(ValueError):
        await service.reattempt_run(player, run.id, reason='')

    voided = await service.reattempt_run(player, run.id, reason='client crash')
    assert voided.reattempted is True
    # Slot freed → the player can draw again despite runs_per_pool=1.
    run2 = await service.start_run(player, q.id, pool.id)
    assert run2.status == AsyncQualifierRunStatus.IN_PROGRESS
    await service.forfeit_run(player, run2.id)
    # Only one reattempt allowed.
    with pytest.raises(ValueError):
        await service.reattempt_run(player, run2.id, reason='again')


async def test_leaderboard_locked_down_while_active(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    player = await _player(900017, 'p1')
    run = await service.start_run(player, q.id, pool.id)
    await service.submit_run(player, run.id, elapsed_seconds=1200)
    await service.review_run(staff, run.id, approved=True)

    # Non-staff cannot see the board while the qualifier is open.
    with pytest.raises(PermissionError):
        await service.get_leaderboard(player, q.id)
    # Staff can.
    board = await service.get_leaderboard(staff, q.id)
    assert board and board[0].actual == 100.0

    # Close the qualifier → board goes public.
    await service.update_qualifier(staff, q.id, is_active=False)
    public = await service.get_leaderboard(player, q.id)
    assert public and public[0].actual == 100.0


async def test_submit_and_review_publish_events(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    player = await _player(900018, 'p1')

    seen = []
    event_bus.subscribe_sync(
        lambda e: seen.append(e.event_type),
        [EventType.ASYNC_QUALIFIER_RUN_SUBMITTED, EventType.ASYNC_QUALIFIER_RUN_REVIEWED],
    )

    run = await service.start_run(player, q.id, pool.id)
    await service.submit_run(player, run.id, elapsed_seconds=1200)
    await service.review_run(staff, run.id, approved=True)
    assert EventType.ASYNC_QUALIFIER_RUN_SUBMITTED in seen
    assert EventType.ASYNC_QUALIFIER_RUN_REVIEWED in seen
