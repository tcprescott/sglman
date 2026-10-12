"""CommunityEventService: submission, review, edits, cancellation, subscriptions, and who hears what."""

from datetime import datetime, timedelta, timezone

import pytest

from application.errors import FeatureDisabledError, NotFoundError
from application.events import EventType
from application.services.audit_service import AuditActions
from application.services.community_event_service import CommunityEventService, EventDraft
from models import (
    AuditLog,
    CommunityEvent,
    CommunityEventStatus,
    CommunityEventSubscription,
    FeatureFlag,
    Role,
    TenantFeatureFlag,
    TenantMembership,
    UserRole,
)
from tests.conftest import DEFAULT_TEST_TENANT_ID
from tests.factories import make_user

pytestmark = pytest.mark.usefixtures("db")


def _soon(hours: float = 5) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _draft(**overrides) -> EventDraft:
    fields = dict(title='Board games', description='**Bring** a game', starts_at=_soon(),
                  duration_minutes=120, location='Room 2')
    fields.update(overrides)
    return EventDraft(**fields)


@pytest.fixture
async def member():
    user = await make_user(discord_id=600, username='host')
    await TenantMembership.create(user=user, tenant_id=DEFAULT_TEST_TENANT_ID)
    return user


@pytest.fixture
async def other_member():
    user = await make_user(discord_id=602, username='fan')
    await TenantMembership.create(user=user, tenant_id=DEFAULT_TEST_TENANT_ID)
    return user


@pytest.fixture
async def staff():
    user = await make_user(discord_id=601, username='staffer')
    await TenantMembership.create(user=user, tenant_id=DEFAULT_TEST_TENANT_ID)
    await UserRole.create(user=user, role=Role.STAFF, tenant_id=DEFAULT_TEST_TENANT_ID)
    return user


@pytest.fixture
def dms(monkeypatch):
    """Each DM's recipient, text and button, recorded as the queue would send them."""
    sent: list = []
    from application.services import discord as discord_pkg
    from application.services.discord import DiscordService

    async def fake_send(self, user_id, message, view_factory=None, embed=None, link=None):
        sent.append({'to': user_id, 'text': message, 'link': link})
        return True, ''

    monkeypatch.setattr(DiscordService, 'send_dm', fake_send)
    pending: list = []
    monkeypatch.setattr(discord_pkg.discord_queue, 'enqueue', pending.append)

    async def flush() -> list:
        """The DMs sent since the last flush."""
        while pending:
            await pending.pop(0)
        batch = list(sent)
        sent.clear()
        return batch

    return flush


async def _actions() -> list[str]:
    return [a.action for a in await AuditLog.all().order_by('id')]


# --- submitting ---------------------------------------------------------------


async def test_a_member_submission_waits_for_review_and_staff_are_told(member, staff, dms):
    event = await CommunityEventService().submit(member, _draft(title='  Board games  '))

    assert event.status is CommunityEventStatus.PENDING
    assert event.title == 'Board games'
    assert await _actions() == [AuditActions.COMMUNITY_EVENT_SUBMITTED]
    sent = await dms()
    assert [d['to'] for d in sent] == [601]
    assert 'Board games' in sent[0]['text']
    assert sent[0]['link'].url.endswith(f'/admin/community-events?community_event={event.id}')


async def test_a_staff_submission_is_listed_straight_away(staff, dms):
    event = await CommunityEventService().submit(staff, _draft())

    assert event.status is CommunityEventStatus.APPROVED
    assert event.reviewed_by_id == staff.id
    assert await _actions() == [
        AuditActions.COMMUNITY_EVENT_SUBMITTED, AuditActions.COMMUNITY_EVENT_APPROVED,
    ]
    assert await dms() == []


async def test_a_non_member_cannot_submit():
    outsider = await make_user(discord_id=603, username='outsider')
    with pytest.raises(PermissionError):
        await CommunityEventService().submit(outsider, _draft())


@pytest.mark.parametrize('overrides, message', [
    ({'title': '   '}, 'title'),
    ({'title': 'x' * 121}, 'title'),
    ({'duration_minutes': 2}, 'between'),
    ({'duration_minutes': 73 * 60}, 'between'),
    ({'starts_at': datetime.now(timezone.utc) - timedelta(minutes=1)}, 'future'),
    ({'starts_at': datetime(2030, 1, 1, 12, 0)}, 'timezone'),
    ({'description': 'x' * 5001}, 'description'),
])
async def test_bad_submissions_are_refused(member, overrides, message):
    with pytest.raises(ValueError, match=message):
        await CommunityEventService().submit(member, _draft(**overrides))
    assert not await CommunityEvent.exists()


# --- visibility -----------------------------------------------------------------


async def test_only_approved_events_are_listed_and_pending_ones_stay_private(member, other_member, staff):
    service = CommunityEventService()
    pending = await service.submit(member, _draft(title='Pending'))
    listed = await service.submit(staff, _draft(title='Listed', starts_at=_soon(2)))

    assert [e.id for e in await service.list_upcoming(other_member)] == [listed.id]
    with pytest.raises(NotFoundError):
        await service.get_event(other_member, pending.id)
    assert (await service.get_event(member, pending.id)).id == pending.id
    assert (await service.get_event(staff, pending.id)).id == pending.id


async def test_an_event_in_progress_stays_listed_until_it_ends(staff, member):
    service = CommunityEventService()
    event = await service.submit(staff, _draft())
    await CommunityEvent.filter(id=event.id).update(
        starts_at=datetime.now(timezone.utc) - timedelta(minutes=30), duration_minutes=60,
    )
    assert [e.id for e in await service.list_upcoming(member)] == [event.id]

    await CommunityEvent.filter(id=event.id).update(duration_minutes=20)
    assert await service.list_upcoming(member) == []


# --- review -------------------------------------------------------------------


async def test_approving_lists_it_and_tells_the_host(member, staff, dms):
    service = CommunityEventService()
    event = await service.submit(member, _draft())
    await dms()

    await service.approve(staff, event.id)

    await event.refresh_from_db()
    assert event.status is CommunityEventStatus.APPROVED
    sent = await dms()
    assert [d['to'] for d in sent] == [600]
    assert sent[0]['link'].url.endswith(f'/community-events/{event.id}')


async def test_rejecting_needs_a_reason_and_sends_it_to_the_host(member, staff, dms):
    service = CommunityEventService()
    event = await service.submit(member, _draft())
    await dms()

    with pytest.raises(ValueError):
        await service.reject(staff, event.id, '  ')
    await service.reject(staff, event.id, 'Pick another room')

    await event.refresh_from_db()
    assert event.status is CommunityEventStatus.REJECTED
    assert event.review_note == 'Pick another room'
    sent = await dms()
    assert [d['to'] for d in sent] == [600]
    assert 'Pick another room' in sent[0]['text']


async def test_only_staff_review(member, other_member):
    service = CommunityEventService()
    event = await service.submit(member, _draft())
    with pytest.raises(PermissionError):
        await service.approve(other_member, event.id)
    with pytest.raises(PermissionError):
        await service.reject(member, event.id, 'no')
    with pytest.raises(PermissionError):
        await service.list_for_review(member)


async def test_taking_a_listed_event_down_tells_its_subscribers(member, other_member, staff, dms):
    service = CommunityEventService()
    event = await service.submit(staff, _draft())
    await service.subscribe(other_member, event.id)

    await service.reject(staff, event.id, 'Venue said no')

    recipients = sorted(d['to'] for d in await dms())
    assert recipients == [601, 602]  # the host (staff here) and the subscriber


# --- edits and cancellation ---------------------------------------------------


async def test_moving_a_listed_event_tells_subscribers_and_rearms_reminders(member, other_member, staff, dms):
    service = CommunityEventService()
    event = await service.submit(member, _draft())
    await service.approve(staff, event.id)
    await service.subscribe(other_member, event.id)
    await CommunityEventSubscription.filter(event_id=event.id).update(reminder_sent_at=datetime.now(timezone.utc))
    await dms()

    await service.update(member, event.id, _draft(starts_at=_soon(8)))

    await event.refresh_from_db()
    assert event.status is CommunityEventStatus.APPROVED
    assert (await CommunityEventSubscription.get(event_id=event.id)).reminder_sent_at is None
    sent = await dms()
    assert [d['to'] for d in sent] == [602]
    assert 'moved' in sent[0]['text']


async def test_editing_text_alone_does_not_ping_subscribers(member, other_member, staff, dms):
    service = CommunityEventService()
    event = await service.submit(staff, _draft())
    await service.subscribe(other_member, event.id)
    await dms()

    await service.update(staff, event.id, _draft(starts_at=event.starts_at, description='New words'))

    assert await dms() == []


async def test_editing_a_rejected_event_resubmits_it(member, staff, dms):
    service = CommunityEventService()
    event = await service.submit(member, _draft())
    await service.reject(staff, event.id, 'Too vague')
    await dms()

    await service.update(member, event.id, _draft(description='Now with details'))

    await event.refresh_from_db()
    assert event.status is CommunityEventStatus.PENDING
    assert [d['to'] for d in await dms()] == [601]


async def test_only_the_host_or_staff_can_edit_or_cancel(member, other_member, staff):
    service = CommunityEventService()
    event = await service.submit(staff, _draft())
    with pytest.raises(PermissionError):
        await service.update(other_member, event.id, _draft())
    with pytest.raises(PermissionError):
        await service.cancel(other_member, event.id)


async def test_cancelling_a_listed_event_tells_subscribers_and_freezes_it(member, other_member, staff, dms):
    service = CommunityEventService()
    event = await service.submit(member, _draft())
    await service.approve(staff, event.id)
    await service.subscribe(other_member, event.id)
    await dms()

    await service.cancel(member, event.id)

    await event.refresh_from_db()
    assert event.status is CommunityEventStatus.CANCELLED
    assert [d['to'] for d in await dms()] == [602]
    assert AuditActions.COMMUNITY_EVENT_CANCELLED in await _actions()
    with pytest.raises(ValueError):
        await service.update(member, event.id, _draft())
    with pytest.raises(ValueError):
        await service.approve(staff, event.id)


# --- subscriptions ------------------------------------------------------------


async def test_subscribing_is_idempotent_and_counted(member, other_member, staff):
    service = CommunityEventService()
    event = await service.submit(staff, _draft())

    await service.subscribe(other_member, event.id)
    await service.subscribe(other_member, event.id)
    await service.subscribe(member, event.id)

    mine, counts = await service.subscription_state(other_member, [event.id])
    assert mine == {event.id}
    assert counts == {event.id: 2}

    await service.unsubscribe(other_member, event.id)
    await service.unsubscribe(other_member, event.id)
    mine, counts = await service.subscription_state(other_member, [event.id])
    assert mine == set()
    assert counts == {event.id: 1}


async def test_you_cannot_subscribe_to_an_unlisted_event(member, other_member):
    service = CommunityEventService()
    event = await service.submit(member, _draft())
    with pytest.raises(NotFoundError):
        await service.subscribe(other_member, event.id)
    with pytest.raises(ValueError):
        await service.subscribe(member, event.id)


async def test_the_flag_being_off_hides_everything(member, staff):
    await TenantFeatureFlag.filter(
        tenant_id=DEFAULT_TEST_TENANT_ID, flag=FeatureFlag.COMMUNITY_EVENTS.value,
    ).update(enabled=False)
    service = CommunityEventService()
    with pytest.raises(FeatureDisabledError):
        await service.list_upcoming(member)
    with pytest.raises(FeatureDisabledError):
        await service.submit(member, _draft())
    with pytest.raises(FeatureDisabledError):
        await service.list_for_review(staff)


async def test_events_are_published_for_webhooks(member, staff, monkeypatch):
    from application.events import event_bus

    published: list = []
    monkeypatch.setattr(event_bus, 'publish', published.append)
    service = CommunityEventService()
    event = await service.submit(member, _draft())
    await service.approve(staff, event.id)

    assert [e.event_type for e in published] == [
        EventType.COMMUNITY_EVENT_SUBMITTED, EventType.COMMUNITY_EVENT_APPROVED,
    ]
    assert published[0].payload['host_id'] == member.id
