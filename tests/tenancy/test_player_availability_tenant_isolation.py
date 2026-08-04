"""Cross-tenant isolation for player availability.

The same person plays in several communities, so their rows are the case where
a missing scope is easy to miss: the user id matches everywhere, and only the
tenant column separates "blocked out for the Cup" from "blocked out for the
Series". Under opt-out a leak reads as a block another community never made.
"""

from datetime import datetime, timezone

from application.repositories.player_availability_repository import (
    PlayerAvailabilityRepository,
)
from application.services.player_availability_service import PlayerAvailabilityService
from application.tenant_context import tenant_scope
from models import PlayerAvailability, User, VolunteerAvailabilityStatus

UTC = timezone.utc
START = datetime(2026, 10, 4, 12, tzinfo=UTC)
END = datetime(2026, 10, 4, 16, tzinfo=UTC)


async def _row(tenant_id, user):
    with tenant_scope(tenant_id):
        return await PlayerAvailability.create(
            tenant_id=tenant_id, user=user, starts_at=START, ends_at=END,
            status=VolunteerAvailabilityStatus.UNAVAILABLE,
        )


async def test_reads_are_isolated(two_tenants):
    a, b = two_tenants
    player = await User.create(discord_id=1, username='jem')
    ra, rb = await _row(a.id, player), await _row(b.id, player)

    repo = PlayerAvailabilityRepository()
    with tenant_scope(a.id):
        assert [r.id for r in await repo.list_for_user(player)] == [ra.id]
        assert [r.id for r in await repo.for_users_overlapping(
            [player.id], START, END,
        )] == [ra.id]
        assert await repo.get_by_id(rb.id) is None
    with tenant_scope(b.id):
        assert [r.id for r in await repo.list_for_user(player)] == [rb.id]
        assert await repo.get_by_id(ra.id) is None


async def test_writes_are_stamped_with_the_active_tenant(two_tenants):
    a, b = two_tenants
    player = await User.create(discord_id=2, username='rue')
    with tenant_scope(b.id):
        created = await PlayerAvailabilityRepository.create(
            user=player, starts_at=START, ends_at=END,
            status=VolunteerAvailabilityStatus.UNAVAILABLE,
        )

    assert created.tenant_id == b.id
    with tenant_scope(a.id):
        assert await PlayerAvailabilityRepository.get_by_id(created.id) is None


async def test_replacing_windows_only_clears_its_own_tenant(two_tenants):
    """`set_windows` deletes-then-creates, which is where a scope goes missing."""
    a, b = two_tenants
    player = await User.create(discord_id=3, username='wren')
    kept = await _row(a.id, player)

    with tenant_scope(b.id):
        await PlayerAvailabilityService().set_windows(
            player,
            [(START, END, VolunteerAvailabilityStatus.PREFERRED, None)],
        )

    with tenant_scope(a.id):
        assert [r.id for r in await PlayerAvailabilityRepository().list_for_user(player)] \
            == [kept.id]


async def test_a_block_in_one_community_does_not_reach_another(two_tenants):
    """The opt-out consequence: an unblocked community must still read available."""
    a, b = two_tenants
    player = await User.create(discord_id=4, username='pip')
    await _row(a.id, player)

    service = PlayerAvailabilityService()
    with tenant_scope(a.id):
        windows = (await service.availability_map([player.id], START, END)).get(player.id, [])
        assert service.covers(windows, START, END) == VolunteerAvailabilityStatus.UNAVAILABLE
    with tenant_scope(b.id):
        windows = (await service.availability_map([player.id], START, END)).get(player.id, [])
        assert service.covers(windows, START, END) == VolunteerAvailabilityStatus.AVAILABLE
