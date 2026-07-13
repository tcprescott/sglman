"""Cross-tenant isolation (leak) tests for the PR 3 racetime models.

``RaceRoomProfile`` and ``RacetimeRoom`` are tenant-scoped, so each tenant must
see only its own rows. ``RacetimeBot`` is *global*, but its authorization grant
(``RacetimeBotTenant``) is per-tenant: a tenant must never surface a category it
was not granted. The by-slug room lookup is deliberately **unscoped** (inbound
racetime events carry no tenant), so it resolves cross-tenant on purpose — that
behavior is asserted too.
"""

from application.repositories.race_room_profile_repository import RaceRoomProfileRepository
from application.repositories.racetime_bot_repository import RacetimeBotRepository
from application.repositories.racetime_room_repository import RacetimeRoomRepository
from application.tenant_context import tenant_scope
from models import RaceRoomProfile, RacetimeBot, RacetimeRoom, Tenant


async def _tenants(db):
    a = await Tenant.get(id=1)
    b = await Tenant.create(name='Tenant B', slug='tenant-b')
    return a, b


async def test_race_room_profile_reads_are_isolated(db):
    a, b = await _tenants(db)
    repo = RaceRoomProfileRepository()
    with tenant_scope(a.id):
        pa = await RaceRoomProfile.create(name='House')
    with tenant_scope(b.id):
        pb = await RaceRoomProfile.create(name='House')  # same name, different tenant

    with tenant_scope(a.id):
        assert [p.id for p in await repo.list_all()] == [pa.id]
        assert await repo.get_by_id(pb.id) is None  # B's profile invisible to A
        assert (await repo.get_by_name('House')).id == pa.id
    with tenant_scope(b.id):
        assert [p.id for p in await repo.list_all()] == [pb.id]
        assert await repo.get_by_id(pa.id) is None


async def test_racetime_room_scoped_reads_are_isolated(db):
    a, b = await _tenants(db)
    repo = RacetimeRoomRepository()
    with tenant_scope(a.id):
        ra = await RacetimeRoom.create(slug='alttpr/room-a', category='alttpr')
    with tenant_scope(b.id):
        rb = await RacetimeRoom.create(slug='alttpr/room-b', category='alttpr')

    with tenant_scope(a.id):
        assert [r.id for r in await repo.list_all()] == [ra.id]
        assert await repo.get_by_id(rb.id) is None  # B's room invisible to A
    with tenant_scope(b.id):
        assert [r.id for r in await repo.list_all()] == [rb.id]


async def test_racetime_room_by_slug_is_unscoped(db):
    """Inbound events carry no tenant, so slug → room resolves cross-tenant."""
    a, b = await _tenants(db)
    repo = RacetimeRoomRepository()
    with tenant_scope(b.id):
        rb = await RacetimeRoom.create(slug='alttpr/only-in-b', category='alttpr')

    # No tenant scope at all — the routing entry point — still resolves it.
    room = await repo.get_by_slug('alttpr/only-in-b')
    assert room is not None and room.id == rb.id
    assert room.tenant_id == b.id


async def test_bot_grants_do_not_leak_across_tenants(db):
    a, b = await _tenants(db)
    repo = RacetimeBotRepository()
    # The bot is global; grant it only to A.
    bot = await RacetimeBot.create(category='alttpr', client_id='c', client_secret='s', name='A')
    await repo.create_grant(bot.id, a.id)

    assert [x.id for x in await repo.list_active_for_tenant(a.id)] == [bot.id]
    # B holds no grant — the global bot must not surface for it.
    assert await repo.list_active_for_tenant(b.id) == []
