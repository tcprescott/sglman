"""Service tests for AsyncQualifierService: draw, run lifecycle, review, scoring, lockdown."""

from datetime import datetime, timedelta, timezone

import pytest

from application.events import EventType, event_bus
from application.services.async_qualifier import async_qualifier_rules as rules
from application.services.async_qualifier.async_qualifier_service import AsyncQualifierService
from models import (
    AsyncQualifierPermalink,
    AsyncQualifierReviewNote,
    AsyncQualifierReviewStatus,
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


async def _player(discord_id: int, name: str, **extra) -> User:
    return await User.create(discord_id=discord_id, username=name, **extra)


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
    # A pool whose preset uses a keyed randomizer (ootr) cannot roll when this
    # community has not configured the key: the first roll raises before any
    # permalink row exists, so the whole batch aborts with nothing half-written.
    # Deliberately not dk64r, which now refuses earlier for being asynchronous
    # (see test_roll_permalinks_refuses_async_randomizer).
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
            name='OOT', randomizer='ootr', settings={'settings_string': 'x'},
        )
        now = datetime.now(timezone.utc)
        q = await service.create_qualifier(
            staff, name='Q', opens_at=now - timedelta(days=1),
            closes_at=now + timedelta(days=1), runs_per_pool=1,
        )
        pool = await service.create_pool(staff, q.id, name='Pool A', preset_id=preset.id)

        with pytest.raises(ValueError, match='OoT Randomizer API key is not configured'):
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


# --- a rejection owes the runner a reason ---------------------------------

async def _pending_run(service, staff, player, *, seconds=1200):
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    run = await service.start_run(player, q.id, pool.id)
    await _submit(service, player, run, seconds)
    return q, pool, run


async def test_rejection_requires_a_reason(db):
    service = AsyncQualifierService()
    staff = await _staff()
    player = await _player(900040, 'p1')
    _, _, run = await _pending_run(service, staff, player)

    with pytest.raises(ValueError, match='A rejection needs a reason'):
        await service.review_run(staff, run.id, approved=False)


async def test_rejection_without_a_reason_changes_nothing(db):
    """The check sits above the note write and the status update."""
    service = AsyncQualifierService()
    staff = await _staff()
    player = await _player(900041, 'p1')
    _, _, run = await _pending_run(service, staff, player)

    with pytest.raises(ValueError):
        await service.review_run(staff, run.id, approved=False, note='   ')

    unchanged = await AsyncQualifierRun.get(id=run.id)
    assert unchanged.review_status == AsyncQualifierReviewStatus.PENDING
    assert unchanged.reviewed_by_id is None
    assert await AsyncQualifierReviewNote.filter(run_id=run.id).count() == 0


async def test_rejection_with_a_reason_stores_a_note(db):
    service = AsyncQualifierService()
    staff = await _staff()
    player = await _player(900042, 'p1')
    _, _, run = await _pending_run(service, staff, player)

    reviewed = await service.review_run(
        staff, run.id, approved=False, note='The VoD cuts off before the final boss.',
    )
    assert reviewed.review_status == AsyncQualifierReviewStatus.REJECTED
    notes = await AsyncQualifierReviewNote.filter(run_id=run.id)
    assert [n.note for n in notes] == ['The VoD cuts off before the final boss.']


async def test_approval_still_works_without_a_note(db):
    service = AsyncQualifierService()
    staff = await _staff()
    player = await _player(900043, 'p1')
    _, _, run = await _pending_run(service, staff, player)

    reviewed = await service.review_run(staff, run.id, approved=True)
    assert reviewed.review_status == AsyncQualifierReviewStatus.APPROVED
    assert await AsyncQualifierReviewNote.filter(run_id=run.id).count() == 0


# --- a remedy someone can actually spend ----------------------------------

@pytest.fixture
def captured_dms(monkeypatch):
    """Capture the DM text the qualifier notifications send.

    The notification module imports ``DiscordService`` lazily inside each
    function, so patching the class where it lives covers both call sites.
    """
    sent: list[tuple[int, str, object]] = []

    class _Fake:
        # Mirrors the real signature: a fake narrower than the thing it stands
        # in for turns an added argument into "no DM was sent at all", which is
        # exactly how the link button first went missing here.
        async def send_dm(self, discord_id, message, view_factory=None, embed=None, link=None):
            sent.append((discord_id, message, link))
            return True, 'ok'

    monkeypatch.setattr(
        'application.services.discord.discord_service.DiscordService', _Fake,
    )
    return sent


async def test_reattempt_allowance_counts_spent_and_remaining(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff, runs_per_pool=1, allowed_reattempts=1)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1', 'u2'])
    player = await _player(900050, 'p1')

    fresh = await service.get_reattempt_allowance(player, q.id)
    assert (fresh.spent, fresh.allowed, fresh.remaining) == (0, 1, 1)

    run = await service.start_run(player, q.id, pool.id)
    await service.forfeit_run(player, run.id)
    await service.reattempt_run(player, run.id, reason='mis-clicked forfeit')

    after = await service.get_reattempt_allowance(player, q.id)
    assert (after.spent, after.allowed, after.remaining) == (1, 1, 0)


async def test_reattempt_frees_the_pool_slot_for_a_new_draw(db):
    """The runner-visible behaviour: a voided run gives the pool slot back."""
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff, runs_per_pool=1, allowed_reattempts=1)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1', 'u2'])
    player = await _player(900051, 'p1')

    first = await service.start_run(player, q.id, pool.id)
    await service.forfeit_run(player, first.id)
    assert await service.get_player_pools(player, q.id) == []

    await service.reattempt_run(player, first.id, reason='the seed would not load')
    assert [p.id for p in await service.get_player_pools(player, q.id)] == [pool.id]

    second = await service.start_run(player, q.id, pool.id)
    assert second.id != first.id
    assert second.status == AsyncQualifierRunStatus.IN_PROGRESS
    # The voided run leaves the played set too, so its permalink is drawable
    # again — a void says the attempt did not happen, not that the seed is spent.


async def test_grant_reattempt_requires_qualifier_admin(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    player = await _player(900052, 'p1')
    other = await _player(900053, 'p2')

    run = await service.start_run(player, q.id, pool.id)
    await service.forfeit_run(player, run.id)

    with pytest.raises(PermissionError):
        await service.grant_reattempt(other, run.id, reason='nope')
    with pytest.raises(PermissionError):
        await service.grant_reattempt(None, run.id, reason='nope')


async def test_grant_reattempt_requires_a_reason(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    player = await _player(900054, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    await service.forfeit_run(player, run.id)
    with pytest.raises(ValueError, match='reattempt reason is required'):
        await service.grant_reattempt(staff, run.id, reason='  ')

    unchanged = await AsyncQualifierRun.get(id=run.id)
    assert unchanged.reattempted is False


async def test_grant_reattempt_ignores_the_runners_allowance(db, captured_dms):
    """The override exists precisely where the runner's own path refuses."""
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff, runs_per_pool=1, allowed_reattempts=0)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1', 'u2'])
    player = await _player(900055, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    await service.forfeit_run(player, run.id)
    with pytest.raises(ValueError, match='No reattempts remaining'):
        await service.reattempt_run(player, run.id, reason='please')

    granted = await service.grant_reattempt(staff, run.id, reason='seed was unbeatable')
    assert granted.reattempted is True
    assert granted.reattempt_granted_by_id == staff.id

    # And it does not eat an allowance the runner never had.
    allowance = await service.get_reattempt_allowance(player, q.id)
    assert (allowance.spent, allowance.remaining) == (0, 0)
    assert captured_dms and 'granted you another attempt' in captured_dms[0][1]
    assert captured_dms[0][2].label == 'Start your next run'


async def test_grant_reattempt_frees_the_slot_after_a_forfeit(db):
    """F1, end to end: a mis-clicked forfeit stops being the end of the attempt."""
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff, runs_per_pool=1, allowed_reattempts=0)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1', 'u2'])
    player = await _player(900056, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    await service.forfeit_run(player, run.id)
    assert await service.get_player_pools(player, q.id) == []

    await service.grant_reattempt(staff, run.id, reason='mis-click, confirmed on stream')
    assert [p.id for p in await service.get_player_pools(player, q.id)] == [pool.id]
    again = await service.start_run(player, q.id, pool.id)
    assert again.status == AsyncQualifierRunStatus.IN_PROGRESS


async def test_grant_reattempt_refreshes_par_and_scores(db):
    """Voiding an approved run must drop it out of the par inputs."""
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff, runs_per_pool=2)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    fast = await _player(900057, 'fast')

    run = await service.start_run(fast, q.id, pool.id)
    permalink_id = run.permalink_id
    await _submit(service, fast, run, 600)
    await service.review_run(staff, run.id, approved=True)
    assert (await AsyncQualifierPermalink.get(id=permalink_id)).par_time == 600

    await service.grant_reattempt(staff, run.id, reason='wrong permalink played')
    assert (await AsyncQualifierPermalink.get(id=permalink_id)).par_time is None


async def test_grant_reattempt_refuses_an_in_progress_run(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    player = await _player(900058, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    with pytest.raises(ValueError, match='finished or forfeited'):
        await service.grant_reattempt(staff, run.id, reason='too early')


async def test_list_runs_requires_qualifier_admin(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    player = await _player(900059, 'p1')
    run = await service.start_run(player, q.id, pool.id)
    await service.forfeit_run(player, run.id)

    with pytest.raises(PermissionError):
        await service.list_runs(player, q.id)
    # A forfeit never reaches the review queue, which is why this read exists.
    assert await service.list_review_queue(staff, q.id) == []
    assert [r.id for r in await service.list_runs(staff, q.id)] == [run.id]


async def test_runner_runs_carry_their_review_notes(db):
    service = AsyncQualifierService()
    staff = await _staff()
    player = await _player(900060, 'p1')
    _, _, run = await _pending_run(service, staff, player)
    await service.review_run(staff, run.id, approved=False, note='VoD ends early.')

    runs = await service.list_user_runs(player, run.qualifier_id)
    assert [n.note for n in runs[0].review_notes] == ['VoD ends early.']


async def test_rejection_dm_includes_the_reason(db, captured_dms):
    service = AsyncQualifierService()
    staff = await _staff()
    player = await _player(900061, 'p1')
    _, _, run = await _pending_run(service, staff, player)

    await service.review_run(staff, run.id, approved=False, note='The VoD cuts off early.')
    assert captured_dms, 'the runner was told nothing'
    _, message, link = captured_dms[-1]
    assert 'rejected' in message
    assert 'Reason: The VoD cuts off early.' in message
    assert f'/qualifiers/{run.qualifier_id}' in message
    # The button, not only the markdown link: an embed suppresses the DM's text
    # content entirely, so a link that lives only in `message` can go unseen.
    assert link is not None and link.url.endswith(f'/qualifiers/{run.qualifier_id}')


async def test_review_queue_carries_existing_notes(db):
    """The reviewer's card renders notes already on the run, so the queue read
    must prefetch them — touching an unfetched relation raises in the page."""
    service = AsyncQualifierService()
    staff = await _staff()
    player = await _player(900062, 'p1')
    q, pool = await _open_qualifier(service, staff, runs_per_pool=2)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1', 'u2'])

    first = await service.start_run(player, q.id, pool.id)
    await _submit(service, player, first, 1200)
    await service.review_run(staff, first.id, approved=False, note='VoD ends early.')
    second = await service.start_run(player, q.id, pool.id)
    await _submit(service, player, second, 1300)

    queue = await service.list_review_queue(staff, q.id)
    assert [[n.note for n in r.review_notes] for r in queue] == [[]]
    runs = await service.list_runs(staff, q.id)
    assert sorted(n.note for r in runs for n in r.review_notes) == ['VoD ends early.']


# --- why you cannot start, specifically -----------------------------------

async def test_availability_lists_pools_when_a_run_can_be_started(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff, runs_per_pool=2)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1', 'u2'])
    player = await _player(900070, 'p1')

    availability = await service.get_run_availability(player, q.id)
    assert [p.id for p in availability.pools] == [pool.id]
    assert availability.reason is None
    assert availability.message == ''
    assert [(u.name, u.used, u.allowed) for u in availability.usage] == [('Pool A', 0, 2)]


async def test_availability_reports_not_open_yet(db):
    service = AsyncQualifierService()
    staff = await _staff()
    now = datetime.now(timezone.utc)
    q = await service.create_qualifier(
        staff, name='Later', opens_at=now + timedelta(days=1), closes_at=now + timedelta(days=2),
    )
    player = await _player(900071, 'p1')

    availability = await service.get_run_availability(player, q.id)
    assert availability.reason is rules.RunUnavailableReason.NOT_OPEN_YET
    assert availability.message.startswith('This qualifier opens ')
    assert availability.pools == []


async def test_availability_reports_closed(db):
    service = AsyncQualifierService()
    staff = await _staff()
    now = datetime.now(timezone.utc)
    q = await service.create_qualifier(
        staff, name='Done', opens_at=now - timedelta(days=2), closes_at=now - timedelta(days=1),
    )
    player = await _player(900072, 'p1')

    availability = await service.get_run_availability(player, q.id)
    assert availability.reason is rules.RunUnavailableReason.CLOSED
    assert 'The leaderboard is below.' in availability.message


async def test_availability_reports_no_pools(db):
    service = AsyncQualifierService()
    staff = await _staff()
    now = datetime.now(timezone.utc)
    q = await service.create_qualifier(
        staff, name='Empty', opens_at=now - timedelta(days=1), closes_at=now + timedelta(days=1),
    )
    player = await _player(900073, 'p1')

    availability = await service.get_run_availability(player, q.id)
    assert availability.reason is rules.RunUnavailableReason.NO_POOLS
    assert 'ask an organiser' in availability.message


async def test_availability_reports_permalinks_exhausted(db):
    """Slots to spare, but every seed in the pool has been played.

    The reason that was never distinguishable from "you're out of runs" — and the
    only one of the two an organiser can fix.
    """
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff, runs_per_pool=3)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    player = await _player(900074, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    await _submit(service, player, run, 1200)

    availability = await service.get_run_availability(player, q.id)
    assert availability.reason is rules.RunUnavailableReason.PERMALINKS_EXHAUSTED
    assert 'An organiser needs to add more.' in availability.message
    assert availability.usage[0].slots_left == 2


async def test_availability_reports_all_slots_used(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff, runs_per_pool=1)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1', 'u2'])
    player = await _player(900075, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    await _submit(service, player, run, 1200)

    availability = await service.get_run_availability(player, q.id)
    assert availability.reason is rules.RunUnavailableReason.ALL_SLOTS_USED
    assert availability.message == "You've used all 1 of your runs in every pool."


async def test_availability_asks_an_anonymous_visitor_to_sign_in(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])

    availability = await service.get_run_availability(None, q.id)
    assert availability.reason is rules.RunUnavailableReason.ANONYMOUS
    assert availability.message == 'Sign in to start a run.'


async def test_get_player_pools_still_raises_for_a_shut_window(db):
    """The REST client depends on the raise; only the web surface switched reads."""
    service = AsyncQualifierService()
    staff = await _staff()
    now = datetime.now(timezone.utc)
    q = await service.create_qualifier(
        staff, name='Shut', opens_at=now - timedelta(days=2), closes_at=now - timedelta(days=1),
    )
    player = await _player(900076, 'p1')
    with pytest.raises(ValueError, match='has closed'):
        await service.get_player_pools(player, q.id)


async def test_availability_ignores_a_live_race_only_pool(db):
    """A pool a self-paced runner can never draw from must not drive the reason.

    Its permalinks are live-race, so it looks forever like "slots free, every seed
    played" — which would tell an organiser to add seeds that already exist.
    """
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff, runs_per_pool=1)
    await service.add_permalinks_bulk(staff, pool.id, urls=['u1'])
    live_pool = await service.create_pool(staff, q.id, name='Live Races')
    live = await service.add_permalink(staff, live_pool.id, url='live-1')
    await service.update_permalink(staff, live.id, live_race=True)
    player = await _player(900077, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    await _submit(service, player, run, 1200)

    availability = await service.get_run_availability(player, q.id)
    assert availability.reason is rules.RunUnavailableReason.ALL_SLOTS_USED
    assert [u.name for u in availability.usage] == ['Pool A']


async def test_availability_reports_no_pools_when_only_live_races_exist(db):
    service = AsyncQualifierService()
    staff = await _staff()
    q, pool = await _open_qualifier(service, staff)
    live = await service.add_permalink(staff, pool.id, url='live-1')
    await service.update_permalink(staff, live.id, live_race=True)
    player = await _player(900078, 'p1')

    availability = await service.get_run_availability(player, q.id)
    assert availability.reason is rules.RunUnavailableReason.NO_POOLS


async def test_roll_permalinks_refuses_async_randomizer(db):
    # A task-queue backend (dk64r) cannot fill a pool yet: each roll takes
    # minutes and lands independently, so the batch's all-or-nothing property
    # would not hold. Refused in the service, not only in the preset picker,
    # because a pool created before dk64r became asynchronous already exists.
    from application.tenant_context import tenant_scope
    from models import FeatureFlag, Preset, Tenant, TenantFeatureFlag

    service = AsyncQualifierService()
    b = await Tenant.create(name='AsyncQ', slug='async-q')
    await TenantFeatureFlag.create(
        tenant_id=b.id, flag=FeatureFlag.ASYNC_QUALIFIERS.value,
        available=True, enabled=True,
    )
    with tenant_scope(b.id):
        staff = await User.create(discord_id=900501, username='qstaff2')
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

        with pytest.raises(ValueError, match='rolls seeds asynchronously'):
            await service.roll_permalinks(staff, pool.id, count=2)

        from models import AsyncQualifierPermalink
        assert await AsyncQualifierPermalink.all().count() == 0
