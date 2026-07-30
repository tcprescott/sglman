"""Service tests for AsyncQualifierService: draw, run lifecycle, review, scoring, lockdown."""

from datetime import datetime, timedelta, timezone

import pytest

from application.events import EventType, event_bus
from application.services.async_qualifier.async_qualifier_service import AsyncQualifierService
from models import (
    AsyncQualifierPermalink,
    AsyncQualifierRun,
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


async def _submit(service, player, run, seconds: int):
    """Submit ``seconds`` on ``run``, backdating the draw so the wall clock agrees.

    ``submit_run`` refuses a claim longer than the run has existed (the server
    stamps ``started_at`` at the draw and measures against it), so a fixture that
    starts a run and immediately claims twenty minutes is claiming the impossible.
    """
    await AsyncQualifierRun.filter(id=run.id).update(
        started_at=datetime.now(timezone.utc) - timedelta(seconds=seconds),
    )
    return await service.submit_run(player, run.id, elapsed_seconds=seconds)


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
    await _submit(service, player, run, 1000)
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
        await _submit(service, player, run, 1000)
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
    await _submit(service, player, run, 1200)
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
    await _submit(service, staff, run, 1200)
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
        await _submit(service, player, run, 1000)


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
    await _submit(service, player, run, 1200)
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
    await _submit(service, player, run, 1200)
    await service.review_run(staff, run.id, approved=True)
    assert EventType.ASYNC_QUALIFIER_RUN_SUBMITTED in seen
    assert EventType.ASYNC_QUALIFIER_RUN_REVIEWED in seen


async def test_roll_permalinks_blocked_when_credential_missing(db):
    # A pool whose preset uses a keyed randomizer (dk64r) cannot roll when this
    # community has not configured the key: the first roll raises before any
    # permalink row exists, so the whole batch aborts with nothing half-written.
    # A fresh tenant is used because the db-fixture tenant would otherwise share
    # any credential a sibling test created.
    #
    # ASYNC_QUALIFIERS is turned on for this tenant so the subject under test is
    # the credential, not AsyncQualifierService's own feature guard (which would
    # refuse create_qualifier first with every flag off).
    from application.tenant_context import tenant_scope
    from models import FeatureFlag, Preset, Tenant, TenantFeatureFlag

    service = AsyncQualifierService()
    b = await Tenant.create(name='NoDK', slug='no-dk-q')
    await TenantFeatureFlag.create(
        tenant_id=b.id, flag=FeatureFlag.ASYNC_QUALIFIERS.value,
        available=True, enabled=True,
    )
    with tenant_scope(b.id):
        staff = await User.create(discord_id=900500, username='qstaff')
        await UserRole.create(user=staff, role=Role.STAFF)
        preset = await Preset.create(
            name='DK', randomizer='dk64r', settings={'settings_string': 'x'},
        )
        now = datetime.now(timezone.utc)
        q = await service.create_qualifier(
            staff, name='Q', opens_at=now - timedelta(days=1),
            closes_at=now + timedelta(days=1), runs_per_pool=1,
        )
        pool = await service.create_pool(staff, q.id, name='Pool A', preset_id=preset.id)

        with pytest.raises(ValueError, match='DK64 Randomizer API key is not configured'):
            await service.roll_permalinks(staff, pool.id, count=2)

        assert await AsyncQualifierPermalink.filter(pool_id=pool.id).count() == 0


# --- the server's own clock as evidence -----------------------------------

async def test_submit_stores_the_server_measured_duration(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    player = await _player(900030, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    submitted = await _submit(service, player, run, 1200)

    # Measured is the wall clock from the draw, not a copy of the claim.
    assert submitted.measured_seconds is not None
    assert 1200 <= submitted.measured_seconds <= 1230
    assert submitted.elapsed_seconds == 1200


async def test_submit_refuses_a_claim_longer_than_the_run_has_existed(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    player = await _player(900031, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    with pytest.raises(ValueError, match='longer than the run itself'):
        await service.submit_run(player, run.id, elapsed_seconds=4462)

    # The refusal must not terminate the run — the player fixes the time and retries.
    still = await AsyncQualifierRun.get(id=run.id)
    assert still.status == AsyncQualifierRunStatus.IN_PROGRESS
    assert still.elapsed_seconds is None


async def test_submit_accepts_an_implausible_claim_and_still_records_it(db):
    """Only the impossible is refused. A large shortfall is the runner's call —
    finishing and submitting an hour later is legitimate — so the service records
    both numbers and lets the reviewer see the gap."""
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    player = await _player(900032, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    await AsyncQualifierRun.filter(id=run.id).update(
        started_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    submitted = await service.submit_run(player, run.id, elapsed_seconds=862)

    assert submitted.status == AsyncQualifierRunStatus.FINISHED
    assert submitted.elapsed_seconds == 862
    assert submitted.measured_seconds >= 7200


async def test_submit_tolerates_a_run_with_no_started_at(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    player = await _player(900033, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    await AsyncQualifierRun.filter(id=run.id).update(started_at=None)
    submitted = await service.submit_run(player, run.id, elapsed_seconds=1200)

    assert submitted.measured_seconds is None
    assert submitted.elapsed_seconds == 1200
