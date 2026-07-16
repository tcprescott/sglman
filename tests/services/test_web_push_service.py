"""Tests for WebPushService: subscription CRUD, config gating, and delivery."""

import json

import pytest

from application.services.web_push_service import WebPushService
from application.utils.web_push import b64url_decode, generate_vapid_keys, load_vapid_private_key
from models import AuditLog, User, WebPushSubscription
from tests.test_web_push_protocol import (
    RFC_AUTH,
    RFC_UA_PRIVATE,
    RFC_UA_PUBLIC,
    decrypt_payload,
)

ENDPOINT = 'https://push.example.net/send/abc123'


from tests.factories import make_user as _user


async def _subscribed_user(discord_id: int = 1) -> User:
    user = await _user(discord_id)
    await WebPushSubscription.create(
        user=user, endpoint=ENDPOINT, p256dh=RFC_UA_PUBLIC, auth=RFC_AUTH,
    )
    return user


@pytest.fixture
def vapid_env(monkeypatch):
    private_key, _ = generate_vapid_keys()
    monkeypatch.setenv('VAPID_PRIVATE_KEY', private_key)
    monkeypatch.setenv('VAPID_SUBJECT', 'mailto:ops@example.com')
    return private_key


@pytest.fixture
def no_vapid_env(monkeypatch):
    monkeypatch.delenv('VAPID_PRIVATE_KEY', raising=False)
    monkeypatch.delenv('VAPID_SUBJECT', raising=False)


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.text = f'status {status_code}'


class FakeClient:
    """Stand-in for the shared httpx.AsyncClient: records posts, returns scripted codes."""

    def __init__(self, status_codes):
        self._status_codes = list(status_codes)
        self.calls = []

    async def post(self, url, content=None, headers=None):
        self.calls.append({'url': url, 'content': content, 'headers': headers})
        return FakeResponse(self._status_codes[len(self.calls) - 1])


@pytest.fixture
def fake_client(monkeypatch):
    def _install(status_codes):
        fake = FakeClient(status_codes)
        monkeypatch.setattr('application.services.web_push_service._get_http_client', lambda: fake)
        return fake
    return _install


# ---------------------------------------------------------------------------
# Configuration gating
# ---------------------------------------------------------------------------


class TestConfiguration:
    def test_unconfigured_without_private_key(self, no_vapid_env):
        assert WebPushService.is_configured() is False
        assert WebPushService.get_public_key() is None

    def test_configured_with_key_and_subject(self, vapid_env):
        assert WebPushService.is_configured() is True
        public_key = WebPushService.get_public_key()
        assert public_key and len(b64url_decode(public_key)) == 65

    def test_key_without_usable_subject_disables(self, monkeypatch):
        private_key, _ = generate_vapid_keys()
        monkeypatch.setenv('VAPID_PRIVATE_KEY', private_key)
        monkeypatch.delenv('VAPID_SUBJECT', raising=False)
        monkeypatch.delenv('BASE_URL', raising=False)
        assert WebPushService.is_configured() is False

    def test_https_base_url_serves_as_subject_fallback(self, monkeypatch):
        private_key, _ = generate_vapid_keys()
        monkeypatch.setenv('VAPID_PRIVATE_KEY', private_key)
        monkeypatch.delenv('VAPID_SUBJECT', raising=False)
        monkeypatch.setenv('BASE_URL', 'https://sgl.example.com')
        assert WebPushService.is_configured() is True

    async def test_mirror_dm_is_noop_when_unconfigured(self, db, no_vapid_env, fake_client):
        fake = fake_client([])
        await _subscribed_user()
        await WebPushService().mirror_dm(1, 'hello')
        assert fake.calls == []

    def test_misconfiguration_warns_once_not_per_call(self, monkeypatch, caplog):
        private_key, _ = generate_vapid_keys()
        monkeypatch.setenv('VAPID_PRIVATE_KEY', private_key)
        monkeypatch.delenv('VAPID_SUBJECT', raising=False)
        monkeypatch.delenv('BASE_URL', raising=False)
        with caplog.at_level('WARNING', logger='application.services.web_push_service'):
            assert WebPushService.is_configured() is False
            assert WebPushService.is_configured() is False
            assert WebPushService.get_public_key() is None
        warnings = [r for r in caplog.records if 'VAPID_SUBJECT' in r.message]
        assert len(warnings) == 1

    def test_mirror_enqueue_skipped_when_unconfigured(self, no_vapid_env, monkeypatch):
        from application.services import discord_service
        enqueued = []
        monkeypatch.setattr(
            'application.services.discord_service.event_dispatch_queue.enqueue', enqueued.append
        )
        discord_service._mirror_dm_to_web_push(1, 'hello')
        assert enqueued == []

    def test_mirror_enqueued_fire_and_forget_when_configured(self, vapid_env, monkeypatch):
        from application.services import discord_service
        enqueued = []
        monkeypatch.setattr(
            'application.services.discord_service.event_dispatch_queue.enqueue', enqueued.append
        )
        discord_service._mirror_dm_to_web_push(1, 'hello')
        assert len(enqueued) == 1
        enqueued[0].close()


# ---------------------------------------------------------------------------
# Subscription CRUD
# ---------------------------------------------------------------------------


class TestSubscriptions:
    async def test_subscribe_stores_and_audits(self, db):
        user = await _user()
        subscription = await WebPushService().subscribe(
            user, endpoint=ENDPOINT, p256dh=RFC_UA_PUBLIC, auth=RFC_AUTH,
            user_agent='Mozilla/5.0 (iPhone)',
        )
        assert subscription.id is not None
        stored = await WebPushSubscription.get(id=subscription.id)
        assert stored.endpoint == ENDPOINT
        assert stored.user_agent == 'Mozilla/5.0 (iPhone)'
        assert await AuditLog.filter(action='web_push.subscribed').count() == 1

    async def test_subscribe_rejects_non_https_endpoint(self, db):
        user = await _user()
        with pytest.raises(ValueError, match='https'):
            await WebPushService().subscribe(
                user, endpoint='http://push.example.net/x', p256dh=RFC_UA_PUBLIC, auth=RFC_AUTH,
            )

    async def test_subscribe_rejects_malformed_keys(self, db):
        user = await _user()
        with pytest.raises(ValueError, match='malformed'):
            await WebPushService().subscribe(
                user, endpoint=ENDPOINT, p256dh='not-a-key', auth=RFC_AUTH,
            )
        with pytest.raises(ValueError, match='malformed'):
            await WebPushService().subscribe(
                user, endpoint=ENDPOINT, p256dh=RFC_UA_PUBLIC, auth='nope',
            )

    async def test_subscribe_rejects_private_host_in_production(self, db, monkeypatch):
        # The stored endpoint is POSTed to server-side, so a private/internal
        # host is an SSRF vector and must be rejected in production.
        monkeypatch.setattr('application.services.web_push_service.is_production', lambda: True)
        monkeypatch.setattr(
            'application.utils.ssrf.socket.getaddrinfo',
            lambda *a, **k: [(0, 0, 0, '', ('10.0.0.5', 0))],
        )
        user = await _user()
        with pytest.raises(ValueError, match='public address'):
            await WebPushService().subscribe(
                user, endpoint='https://internal.example/push', p256dh=RFC_UA_PUBLIC, auth=RFC_AUTH,
            )

    async def test_subscribe_allows_public_host_in_production(self, db, monkeypatch):
        monkeypatch.setattr('application.services.web_push_service.is_production', lambda: True)
        monkeypatch.setattr(
            'application.utils.ssrf.socket.getaddrinfo',
            lambda *a, **k: [(0, 0, 0, '', ('93.184.216.34', 0))],
        )
        user = await _user()
        sub = await WebPushService().subscribe(
            user, endpoint=ENDPOINT, p256dh=RFC_UA_PUBLIC, auth=RFC_AUTH,
        )
        assert sub.id is not None

    async def test_subscribe_skips_ssrf_check_outside_production(self, db, monkeypatch):
        # Dev allows private endpoints (mirrors the webhook guard) and never even
        # resolves the host.
        monkeypatch.setattr('application.services.web_push_service.is_production', lambda: False)

        def _boom(*a, **k):
            raise AssertionError('getaddrinfo must not run outside production')

        monkeypatch.setattr('application.utils.ssrf.socket.getaddrinfo', _boom)
        user = await _user()
        sub = await WebPushService().subscribe(
            user, endpoint='https://10.0.0.5/push', p256dh=RFC_UA_PUBLIC, auth=RFC_AUTH,
        )
        assert sub.id is not None

    async def test_resubscribe_rebinds_endpoint_to_new_user(self, db):
        first = await _subscribed_user(discord_id=1)
        second = await _user(discord_id=2)
        await WebPushService().subscribe(
            second, endpoint=ENDPOINT, p256dh=RFC_UA_PUBLIC, auth=RFC_AUTH,
        )
        assert await WebPushSubscription.all().count() == 1
        stored = await WebPushSubscription.get(endpoint=ENDPOINT)
        assert stored.user_id == second.id
        assert stored.user_id != first.id

    async def test_unsubscribe_removes_own_subscription(self, db):
        user = await _subscribed_user()
        assert await WebPushService().unsubscribe(user, ENDPOINT) is True
        assert await WebPushSubscription.all().count() == 0
        assert await AuditLog.filter(action='web_push.unsubscribed').count() == 1

    async def test_unsubscribe_ignores_other_users_endpoint(self, db):
        await _subscribed_user(discord_id=1)
        other = await _user(discord_id=2)
        assert await WebPushService().unsubscribe(other, ENDPOINT) is False
        assert await WebPushSubscription.all().count() == 1

    async def test_remove_subscription_rejects_other_users(self, db):
        owner = await _subscribed_user(discord_id=1)
        other = await _user(discord_id=2)
        subscription = (await WebPushService().list_subscriptions(owner))[0]
        with pytest.raises(ValueError, match='not found'):
            await WebPushService().remove_subscription(other, subscription.id)

    async def test_upsert_recovers_from_lost_insert_race(self, db, monkeypatch):
        from application.repositories import WebPushRepository
        user = await _subscribed_user(discord_id=1)
        repo = WebPushRepository()
        # Simulate the double-click race: the pre-insert existence check misses
        # the row the concurrent handler just created, so create() hits the
        # unique endpoint constraint and must fall back to updating that row.
        real_get = WebPushRepository.get_by_endpoint
        calls = {'n': 0}

        async def racy_get(self, endpoint):
            calls['n'] += 1
            if calls['n'] == 1:
                return None
            return await real_get(self, endpoint)

        monkeypatch.setattr(WebPushRepository, 'get_by_endpoint', racy_get)
        subscription = await repo.upsert(user, ENDPOINT, RFC_UA_PUBLIC, RFC_AUTH, 'ua')
        assert subscription.endpoint == ENDPOINT
        assert await WebPushSubscription.all().count() == 1


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


class TestDelivery:
    async def test_mirror_dm_sends_declarative_payload(self, db, vapid_env, fake_client):
        fake = fake_client([201])
        await _subscribed_user(discord_id=42)

        await WebPushService().mirror_dm(42, '**Match scheduled** today for player__one!')

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call['url'] == ENDPOINT
        assert call['headers']['Content-Encoding'] == 'aes128gcm'
        assert call['headers']['TTL'] == str(WebPushService.TTL_SECONDS)
        assert call['headers']['Urgency'] == 'high'
        assert call['headers']['Authorization'].startswith('vapid t=')

        plaintext = decrypt_payload(
            call['content'], load_vapid_private_key(RFC_UA_PRIVATE), b64url_decode(RFC_AUTH)
        )
        payload = json.loads(plaintext)
        assert payload['web_push'] == 8030
        # Template bold is stripped, but literal __ in names must survive.
        assert payload['notification']['body'] == 'Match scheduled today for player__one!'
        assert payload['notification']['title'] == 'SGL On Site'
        assert payload['notification']['navigate']

        stored = await WebPushSubscription.get(endpoint=ENDPOINT)
        assert stored.last_used_at is not None

    async def test_mirror_dm_without_subscriptions_makes_no_requests(self, db, vapid_env, fake_client):
        fake = fake_client([])
        await _user(discord_id=42)
        await WebPushService().mirror_dm(42, 'hello')
        assert fake.calls == []

    async def test_expired_subscription_is_pruned(self, db, vapid_env, fake_client):
        fake = fake_client([410])
        user = await _subscribed_user(discord_id=42)

        delivered = await WebPushService().notify_user(user, title='t', body='b')

        assert delivered == 0
        assert len(fake.calls) == 1
        assert await WebPushSubscription.all().count() == 0

    async def test_transient_failure_keeps_subscription(self, db, vapid_env, fake_client):
        fake = fake_client([500])
        user = await _subscribed_user(discord_id=42)

        delivered = await WebPushService().notify_user(user, title='t', body='b')

        assert delivered == 0
        assert len(fake.calls) == 1
        assert await WebPushSubscription.all().count() == 1

    async def test_notify_user_counts_deliveries_across_devices(self, db, vapid_env, fake_client):
        fake = fake_client([201, 201])
        user = await _subscribed_user(discord_id=42)
        await WebPushSubscription.create(
            user=user, endpoint=ENDPOINT + '-second', p256dh=RFC_UA_PUBLIC, auth=RFC_AUTH,
        )

        delivered = await WebPushService().notify_user(user, title='t', body='b')

        assert delivered == 2
        assert len(fake.calls) == 2

    async def test_mirror_dm_never_raises(self, db, vapid_env, monkeypatch):
        async def _boom(*args, **kwargs):
            raise RuntimeError('push service down')
        monkeypatch.setattr(WebPushService, '_send_to_subscriptions', _boom)
        await _subscribed_user(discord_id=42)
        # Must swallow the failure — the DM path depends on it.
        await WebPushService().mirror_dm(42, 'hello')
