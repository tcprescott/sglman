"""Tests for the unauthenticated /api/web-push/rotate endpoint.

Its caller is the service worker's ``pushsubscriptionchange`` handler, which has
no session and no bearer token — so the endpoint must work without auth, and the
old subscription's ``auth`` secret has to be doing the authenticating.
"""

from application.utils.web_push import generate_vapid_keys
from models import User, WebPushSubscription
from tests.api_helpers import build_api_app, client_for
from tests.test_web_push_protocol import RFC_AUTH, RFC_UA_PUBLIC

OLD_ENDPOINT = 'https://push.example.net/send/old'
NEW_ENDPOINT = 'https://push.example.net/send/new'
NEW_P256DH = generate_vapid_keys()[1]
NEW_AUTH = 'MTIzNDU2Nzg5YWJjZGVmZw'


async def _subscribed() -> WebPushSubscription:
    user = await User.create(discord_id=4242, username='pusher')
    return await WebPushSubscription.create(
        user=user, endpoint=OLD_ENDPOINT, p256dh=RFC_UA_PUBLIC, auth=RFC_AUTH,
    )


def _body(**overrides) -> dict:
    return {
        'old_endpoint': OLD_ENDPOINT,
        'old_auth': RFC_AUTH,
        'endpoint': NEW_ENDPOINT,
        'p256dh': NEW_P256DH,
        'auth': NEW_AUTH,
        **overrides,
    }


async def test_rotate_succeeds_without_a_bearer_token(db):
    subscription = await _subscribed()
    app = build_api_app()
    async with client_for(app) as client:
        resp = await client.post('/api/web-push/rotate', json=_body())
    assert resp.status_code == 200
    assert resp.json() == {'rotated': True}
    assert (await WebPushSubscription.get(id=subscription.id)).endpoint == NEW_ENDPOINT


async def test_rotate_404s_without_the_old_auth_secret(db):
    subscription = await _subscribed()
    app = build_api_app()
    async with client_for(app) as client:
        resp = await client.post('/api/web-push/rotate', json=_body(old_auth=NEW_AUTH))
    assert resp.status_code == 404
    assert (await WebPushSubscription.get(id=subscription.id)).endpoint == OLD_ENDPOINT


async def test_rotate_404s_for_an_unknown_endpoint(db):
    await _subscribed()
    app = build_api_app()
    async with client_for(app) as client:
        resp = await client.post(
            '/api/web-push/rotate', json=_body(old_endpoint='https://push.example.net/send/nope')
        )
    assert resp.status_code == 404


async def test_rotate_400s_on_a_malformed_new_subscription(db):
    await _subscribed()
    app = build_api_app()
    async with client_for(app) as client:
        resp = await client.post('/api/web-push/rotate', json=_body(p256dh='not-a-key'))
    assert resp.status_code == 400
