"""Why a player cannot start a run — specifically, and in the runner's words.

Split from ``test_async_qualifier_service.py`` when that module approached the
800-line guideline. ``get_run_availability`` is the one read that never raises
for a shut door: a closed window, an empty pool, a pool whose permalinks are
spent and a player who has used every slot are all *answers*, each with the
sentence the run surface owes the person reading it. That makes it a subject of
its own rather than more of the lifecycle the sibling covers.
"""

from datetime import datetime, timedelta, timezone

import pytest

from application.services.async_qualifier import async_qualifier_rules as rules
from application.services.async_qualifier.async_qualifier_service import AsyncQualifierService
from tests.services._async_qualifier_setup import (
    make_player,
    make_staff,
    open_qualifier,
    submit,
)

pytestmark = pytest.mark.anyio


async def test_availability_lists_pools_when_a_run_can_be_started(db):
    service = AsyncQualifierService()
    staff = await make_staff()
    q, pool = await open_qualifier(service, staff, runs_per_pool=2)
    await service.add_permalinks_bulk(staff, pool.id, urls=['https://seed.test/u1', 'https://seed.test/u2'])
    player = await make_player(900070, 'p1')

    availability = await service.get_run_availability(player, q.id)
    assert [p.id for p in availability.pools] == [pool.id]
    assert availability.reason is None
    assert availability.message == ''
    assert [(u.name, u.used, u.allowed) for u in availability.usage] == [('Pool A', 0, 2)]


async def test_availability_reports_not_open_yet(db):
    service = AsyncQualifierService()
    staff = await make_staff()
    now = datetime.now(timezone.utc)
    q = await service.create_qualifier(
        staff, name='Later', opens_at=now + timedelta(days=1), closes_at=now + timedelta(days=2),
    )
    player = await make_player(900071, 'p1')

    availability = await service.get_run_availability(player, q.id)
    assert availability.reason is rules.RunUnavailableReason.NOT_OPEN_YET
    assert availability.message.startswith('This qualifier opens ')
    assert availability.pools == []


async def test_availability_reports_closed(db):
    service = AsyncQualifierService()
    staff = await make_staff()
    now = datetime.now(timezone.utc)
    q = await service.create_qualifier(
        staff, name='Done', opens_at=now - timedelta(days=2), closes_at=now - timedelta(days=1),
    )
    player = await make_player(900072, 'p1')

    availability = await service.get_run_availability(player, q.id)
    assert availability.reason is rules.RunUnavailableReason.CLOSED
    assert 'The leaderboard is below.' in availability.message


async def test_availability_reports_no_pools(db):
    service = AsyncQualifierService()
    staff = await make_staff()
    now = datetime.now(timezone.utc)
    q = await service.create_qualifier(
        staff, name='Empty', opens_at=now - timedelta(days=1), closes_at=now + timedelta(days=1),
    )
    player = await make_player(900073, 'p1')

    availability = await service.get_run_availability(player, q.id)
    assert availability.reason is rules.RunUnavailableReason.NO_POOLS
    assert 'ask an organiser' in availability.message


async def test_availability_reports_permalinks_exhausted(db):
    """Slots to spare, but every seed in the pool has been played.

    The reason that was never distinguishable from "you're out of runs" — and the
    only one of the two an organiser can fix.
    """
    service = AsyncQualifierService()
    staff = await make_staff()
    q, pool = await open_qualifier(service, staff, runs_per_pool=3)
    await service.add_permalinks_bulk(staff, pool.id, urls=['https://seed.test/u1'])
    player = await make_player(900074, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    await submit(service, player, run, 1200)

    availability = await service.get_run_availability(player, q.id)
    assert availability.reason is rules.RunUnavailableReason.PERMALINKS_EXHAUSTED
    assert 'An organiser needs to add more.' in availability.message
    assert availability.usage[0].slots_left == 2


async def test_availability_reports_all_slots_used(db):
    service = AsyncQualifierService()
    staff = await make_staff()
    q, pool = await open_qualifier(service, staff, runs_per_pool=1)
    await service.add_permalinks_bulk(staff, pool.id, urls=['https://seed.test/u1', 'https://seed.test/u2'])
    player = await make_player(900075, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    await submit(service, player, run, 1200)

    availability = await service.get_run_availability(player, q.id)
    assert availability.reason is rules.RunUnavailableReason.ALL_SLOTS_USED
    assert availability.message == "You've used all 1 of your runs in every pool."


async def test_availability_asks_an_anonymous_visitor_to_sign_in(db):
    service = AsyncQualifierService()
    staff = await make_staff()
    q, pool = await open_qualifier(service, staff)
    await service.add_permalinks_bulk(staff, pool.id, urls=['https://seed.test/u1'])

    availability = await service.get_run_availability(None, q.id)
    assert availability.reason is rules.RunUnavailableReason.ANONYMOUS
    assert availability.message == 'Sign in to start a run.'


async def test_get_player_pools_still_raises_for_a_shut_window(db):
    """The REST client depends on the raise; only the web surface switched reads."""
    service = AsyncQualifierService()
    staff = await make_staff()
    now = datetime.now(timezone.utc)
    q = await service.create_qualifier(
        staff, name='Shut', opens_at=now - timedelta(days=2), closes_at=now - timedelta(days=1),
    )
    player = await make_player(900076, 'p1')
    with pytest.raises(ValueError, match='has closed'):
        await service.get_player_pools(player, q.id)


async def test_availability_ignores_a_live_race_only_pool(db):
    """A pool a self-paced runner can never draw from must not drive the reason.

    Its permalinks are live-race, so it looks forever like "slots free, every seed
    played" — which would tell an organiser to add seeds that already exist.
    """
    service = AsyncQualifierService()
    staff = await make_staff()
    q, pool = await open_qualifier(service, staff, runs_per_pool=1)
    await service.add_permalinks_bulk(staff, pool.id, urls=['https://seed.test/u1'])
    live_pool = await service.create_pool(staff, q.id, name='Live Races')
    live = await service.add_permalink(staff, live_pool.id, url='https://seed.test/live-1')
    await service.update_permalink(staff, live.id, live_race=True)
    player = await make_player(900077, 'p1')

    run = await service.start_run(player, q.id, pool.id)
    await submit(service, player, run, 1200)

    availability = await service.get_run_availability(player, q.id)
    assert availability.reason is rules.RunUnavailableReason.ALL_SLOTS_USED
    assert [u.name for u in availability.usage] == ['Pool A']


async def test_availability_reports_no_pools_when_only_live_races_exist(db):
    service = AsyncQualifierService()
    staff = await make_staff()
    q, pool = await open_qualifier(service, staff)
    live = await service.add_permalink(staff, pool.id, url='https://seed.test/live-1')
    await service.update_permalink(staff, live.id, live_race=True)
    player = await make_player(900078, 'p1')

    availability = await service.get_run_availability(player, q.id)
    assert availability.reason is rules.RunUnavailableReason.NO_POOLS
