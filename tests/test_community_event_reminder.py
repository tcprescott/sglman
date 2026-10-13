"""The community event reminder loop.

Drives ``_tick`` against the in-memory ORM: which subscriptions it picks up, the
once-only stamp, the community's lead time, and the feature flag.
"""

from datetime import datetime, timedelta, timezone

import pytest

import application.services.community_event_reminder as worker
from application.services.system_config_service import KEY_COMMUNITY_EVENT_REMINDER_LEAD_MINUTES
from models import (
    CommunityEvent,
    CommunityEventStatus,
    CommunityEventSubscription,
    FeatureFlag,
    SystemConfiguration,
    TenantFeatureFlag,
)
from tests.conftest import DEFAULT_TEST_TENANT_ID
from tests.factories import make_user

pytestmark = pytest.mark.usefixtures("db")


async def _subscription(*, minutes_ahead: float, status=CommunityEventStatus.APPROVED,
                        dm_notifications: bool = True) -> CommunityEventSubscription:
    host = await make_user(discord_id=int(minutes_ahead * 10) + 9000, username=f'host{minutes_ahead}')
    fan = await make_user(discord_id=int(minutes_ahead * 10) + 9500, username=f'fan{minutes_ahead}')
    if not dm_notifications:
        fan.dm_notifications = False
        await fan.save()
    event = await CommunityEvent.create(
        tenant_id=DEFAULT_TEST_TENANT_ID, host=host, title='Board games', status=status,
        starts_at=datetime.now(timezone.utc) + timedelta(minutes=minutes_ahead), duration_minutes=60,
    )
    return await CommunityEventSubscription.create(tenant_id=DEFAULT_TEST_TENANT_ID, event=event, user=fan)


async def _stamped(subscription) -> bool:
    return (await CommunityEventSubscription.get(id=subscription.id)).reminder_sent_at is not None


async def test_reminds_once_inside_the_default_lead(stub_discord_queue):
    subscription = await _subscription(minutes_ahead=20)

    await worker._tick()
    assert len(stub_discord_queue) == 1
    assert await _stamped(subscription)

    for coro in stub_discord_queue:
        coro.close()
    stub_discord_queue.clear()
    await worker._tick()
    assert stub_discord_queue == []


async def test_waits_until_the_event_is_inside_the_lead(stub_discord_queue):
    subscription = await _subscription(minutes_ahead=45)

    await worker._tick()

    assert stub_discord_queue == []
    assert not await _stamped(subscription)


async def test_follows_the_communitys_lead_setting(stub_discord_queue):
    await SystemConfiguration.create(
        tenant_id=DEFAULT_TEST_TENANT_ID, name=KEY_COMMUNITY_EVENT_REMINDER_LEAD_MINUTES, value='60',
    )
    subscription = await _subscription(minutes_ahead=45)

    await worker._tick()

    assert len(stub_discord_queue) == 1
    assert await _stamped(subscription)


async def test_skips_events_that_are_not_listed(stub_discord_queue):
    subscription = await _subscription(minutes_ahead=10, status=CommunityEventStatus.CANCELLED)

    await worker._tick()

    assert stub_discord_queue == []
    assert not await _stamped(subscription)


async def test_someone_with_discord_off_still_reaches_send_dm(stub_discord_queue):
    subscription = await _subscription(minutes_ahead=10, dm_notifications=False)

    await worker._tick()

    # Discord off only drops the Discord copy, inside send_dm; devices still need the call.
    assert len(stub_discord_queue) == 1
    assert await _stamped(subscription)


async def test_does_nothing_where_the_feature_is_off(stub_discord_queue):
    await TenantFeatureFlag.filter(
        tenant_id=DEFAULT_TEST_TENANT_ID, flag=FeatureFlag.COMMUNITY_EVENTS.value,
    ).update(enabled=False)
    subscription = await _subscription(minutes_ahead=10)

    await worker._tick()

    assert stub_discord_queue == []
    assert not await _stamped(subscription)
