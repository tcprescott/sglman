"""Check-in events and their rosters never cross communities.

Two communities can run check-in for the same Matcherino bounty (a shared
event), and the same person can be on both rosters; each community's desk must
see only its own.
"""

import pytest

from application.services.check_in_service import CheckInService
from application.tenant_context import tenant_scope
from application.utils.clients.matcherino_client import MockMatcherinoClient, mock_participant
from models import CheckInEntrant, CheckInEvent, Role, UserRole
from tests.factories import make_user

BOUNTY = 182107


async def test_events_and_rosters_do_not_leak_across_tenants(two_tenants):
    a, b = two_tenants
    staff = await make_user(discord_id=800, username='both-staff')
    player = await make_user(discord_id=801, username='player')
    for tenant in (a, b):
        await UserRole.create(user=staff, role=Role.STAFF, tenant=tenant)

    service = CheckInService(client=MockMatcherinoClient(
        [mock_participant(100, 'Player', auth_provider='discord', auth_id='801')],
    ))
    with tenant_scope(a.id):
        event_a = await service.create_event(staff, 'A event', bounty_id=BOUNTY)
        await service.sync_event(staff, event_a.id)
        entrant_a = (await service.roster(event_a))[0]

    with tenant_scope(b.id):
        # The same bounty is free in B: uniqueness is per community.
        event_b = await service.create_event(staff, 'B event', bounty_id=BOUNTY)
        assert [e.id for e in await service.list_events()] == [event_b.id]
        assert await service.get_event(event_a.id) is None
        assert await service.get_entrant(entrant_a.id) is None
        with pytest.raises(ValueError):
            await service.check_in(staff, entrant_a.id)
        with pytest.raises(ValueError):
            await service.sync_event(staff, event_a.id)
        await service.sync_event(staff, event_b.id)
        entrant_b = (await service.roster(event_b))[0]

    assert entrant_a.id != entrant_b.id
    assert entrant_a.user_id == entrant_b.user_id == player.id
    await entrant_a.refresh_from_db()
    assert entrant_a.checked_in_at is None
    assert await CheckInEvent.all().count() == 2
    assert await CheckInEntrant.filter(tenant_id=a.id).count() == 1


async def test_the_worker_scan_is_cross_tenant_but_each_sync_stays_home(two_tenants, monkeypatch):
    from application.services import check_in_sync_worker
    from models import CheckInEventStatus

    a, b = two_tenants
    staff = await make_user(discord_id=810, username='s')
    for tenant in (a, b):
        await UserRole.create(user=staff, role=Role.STAFF, tenant=tenant)
    monkeypatch.setattr(
        'application.services.check_in_service.get_matcherino_client',
        lambda: MockMatcherinoClient([mock_participant(100, 'P')]),
    )
    service = CheckInService()
    for tenant in (a, b):
        with tenant_scope(tenant.id):
            await service.create_event(staff, f'{tenant.slug} event', bounty_id=BOUNTY,
                                       status=CheckInEventStatus.OPEN)

    await check_in_sync_worker._tick()

    for tenant in (a, b):
        rows = await CheckInEntrant.filter(tenant_id=tenant.id).prefetch_related('event')
        assert len(rows) == 1
        assert rows[0].event.tenant_id == tenant.id
