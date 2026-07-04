"""
Web Push Service - Business Logic Layer

Per-device browser push notifications ("Device Notifications"). Users
subscribe from the settings UI; every Discord DM the app sends is mirrored to
the recipient's subscribed devices, so iOS and Android users get native
notifications without needing the Discord app.

Messages are sent in the **Declarative Web Push** shape (``web_push: 8030`` +
a ``notification`` member): Safari 18.4+ / iOS 18.4+ displays them without
waking a service worker, while Chrome/Android falls back to the ``push``
handler in ``static/sw.js`` which renders the same JSON. Encryption and VAPID
signing live in ``application/utils/web_push.py``.

The feature is enabled by setting ``VAPID_PRIVATE_KEY`` (and optionally
``VAPID_SUBJECT``); without it every send is a silent no-op and the settings
UI hides itself.
"""

import json
import logging
import os
import re
from functools import lru_cache
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives.asymmetric import ec

from application.repositories import WebPushRepository
from application.services.audit_service import AuditActions, AuditService
from application.utils import web_push as protocol
from models import User, WebPushSubscription

logger = logging.getLogger(__name__)

# Magic value that opts a push message into declarative parsing (Safari 18.4+).
DECLARATIVE_WEB_PUSH_VERSION = 8030

# Discord markdown tokens that would render as noise in a native notification.
_MARKDOWN_TOKENS = re.compile(r'\*\*|__|~~|`')


@lru_cache(maxsize=4)
def _parse_private_key(value: str) -> ec.EllipticCurvePrivateKey:
    return protocol.load_vapid_private_key(value)


def _vapid_config() -> Optional[Tuple[ec.EllipticCurvePrivateKey, str]]:
    """Resolve (private_key, subject) from the environment, or None if unset/invalid."""
    raw_key = (os.environ.get('VAPID_PRIVATE_KEY') or '').strip()
    if not raw_key:
        return None
    subject = (os.environ.get('VAPID_SUBJECT') or '').strip()
    if not subject:
        # RFC 8292 wants a mailto: or https: contact; a production BASE_URL
        # qualifies, so it is the natural fallback.
        base_url = (os.environ.get('BASE_URL') or '').strip().rstrip('/')
        if base_url.startswith('https://'):
            subject = base_url
    if not (subject.startswith('mailto:') or subject.startswith('https://')):
        logger.warning(
            'VAPID_PRIVATE_KEY is set but no usable VAPID_SUBJECT '
            '(need mailto:... or https://...); web push disabled'
        )
        return None
    try:
        return _parse_private_key(raw_key), subject
    except (ValueError, TypeError) as exc:
        logger.warning('Invalid VAPID_PRIVATE_KEY; web push disabled: %s', exc)
        return None


class WebPushService:
    """Subscription CRUD plus the encrypted delivery path for web push."""

    DELIVERY_TIMEOUT = 10.0
    TTL_SECONDS = 24 * 60 * 60
    # DM mirrors are time-sensitive (match starting, please acknowledge).
    URGENCY = 'high'
    MAX_BODY_LENGTH = 500

    def __init__(self) -> None:
        self.repository = WebPushRepository()
        self.audit_service = AuditService()

    # ------------------------------------------------------------ config

    @staticmethod
    def is_configured() -> bool:
        return _vapid_config() is not None

    @staticmethod
    def get_public_key() -> Optional[str]:
        """The base64url applicationServerKey browsers subscribe with."""
        config = _vapid_config()
        if config is None:
            return None
        return protocol.public_key_b64url(config[0])

    # ------------------------------------------------------- subscriptions

    async def list_subscriptions(self, user: User) -> List[WebPushSubscription]:
        return await self.repository.list_for_user(user)

    async def subscribe(
        self,
        user: User,
        *,
        endpoint: str,
        p256dh: str,
        auth: str,
        user_agent: Optional[str] = None,
    ) -> WebPushSubscription:
        """Store (or re-bind) a browser PushSubscription for ``user``."""
        endpoint = (endpoint or '').strip()
        parsed = urlparse(endpoint)
        if parsed.scheme != 'https' or not parsed.hostname:
            raise ValueError('Push subscription endpoint must be an https:// URL')
        if len(endpoint) > 1024:
            raise ValueError('Push subscription endpoint is too long')
        try:
            if len(protocol.b64url_decode(p256dh or '')) != 65:
                raise ValueError
            if len(protocol.b64url_decode(auth or '')) != 16:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError('Push subscription keys are malformed')

        subscription = await self.repository.upsert(
            user, endpoint, p256dh, auth, (user_agent or '')[:255] or None
        )
        await self.audit_service.write_log(
            user,
            AuditActions.WEB_PUSH_SUBSCRIBED,
            {'subscription_id': subscription.id, 'endpoint_host': parsed.hostname},
        )
        return subscription

    async def unsubscribe(self, user: User, endpoint: str) -> bool:
        """Remove ``user``'s subscription for ``endpoint``; True if one existed."""
        subscription = await self.repository.get_by_endpoint((endpoint or '').strip())
        if subscription is None or subscription.user_id != user.id:
            return False
        await self.repository.delete(subscription)
        await self.audit_service.write_log(
            user,
            AuditActions.WEB_PUSH_UNSUBSCRIBED,
            {'subscription_id': subscription.id, 'endpoint_host': urlparse(subscription.endpoint).hostname},
        )
        return True

    async def remove_subscription(self, user: User, subscription_id: int) -> None:
        """Remove one of ``user``'s own subscriptions from the device list UI.

        The browser-side subscription stays alive; the server just stops
        sending to it (and would prune it on the next expired delivery).
        """
        subscription = await self.repository.get_by_id(subscription_id)
        if subscription is None or subscription.user_id != user.id:
            raise ValueError('Subscription not found')
        await self.repository.delete(subscription)
        await self.audit_service.write_log(
            user,
            AuditActions.WEB_PUSH_UNSUBSCRIBED,
            {'subscription_id': subscription.id, 'endpoint_host': urlparse(subscription.endpoint).hostname},
        )

    # ------------------------------------------------------------ delivery

    async def mirror_dm(self, discord_id: int, message: str) -> None:
        """Mirror a Discord DM to the recipient's subscribed devices.

        Called from the DM chokepoint for every outgoing DM; must never raise
        and must stay cheap when the user has no subscriptions (one indexed
        query). Runs on the discord_queue worker, off the request path.
        """
        try:
            if not self.is_configured():
                return
            subscriptions = await self.repository.list_for_discord_id(discord_id)
            if not subscriptions:
                return
            await self._send_to_subscriptions(
                subscriptions,
                title='SGL On Site',
                body=self._plain_text(message),
            )
        except Exception:
            logger.exception('web push DM mirror failed for discord id %s', discord_id)

    async def notify_user(
        self,
        user: User,
        *,
        title: str,
        body: str,
        navigate: Optional[str] = None,
    ) -> int:
        """Send a notification to every device ``user`` subscribed. Returns the delivered count."""
        if not self.is_configured():
            return 0
        subscriptions = await self.repository.list_for_user(user)
        if not subscriptions:
            return 0
        return await self._send_to_subscriptions(
            subscriptions, title=title, body=self._plain_text(body), navigate=navigate
        )

    # ----------------------------------------------------------- internals

    def _plain_text(self, message: str) -> str:
        text = _MARKDOWN_TOKENS.sub('', message or '').strip()
        if len(text) > self.MAX_BODY_LENGTH:
            text = text[: self.MAX_BODY_LENGTH - 1] + '…'
        return text

    def _build_payload(self, *, title: str, body: str, navigate: Optional[str] = None) -> bytes:
        """The Declarative Web Push message body (also parsed by sw.js on Chrome)."""
        base_url = (os.environ.get('BASE_URL') or 'http://localhost:8000').rstrip('/')
        return json.dumps({
            'web_push': DECLARATIVE_WEB_PUSH_VERSION,
            'notification': {
                'title': title,
                'body': body,
                'navigate': navigate or f'{base_url}/',
            },
        }, ensure_ascii=False).encode()

    async def _send_to_subscriptions(
        self,
        subscriptions: List[WebPushSubscription],
        *,
        title: str,
        body: str,
        navigate: Optional[str] = None,
    ) -> int:
        config = _vapid_config()
        if config is None:
            return 0
        private_key, subject = config
        payload = self._build_payload(title=title, body=body, navigate=navigate)
        delivered = 0
        async with httpx.AsyncClient(timeout=self.DELIVERY_TIMEOUT) as client:
            for subscription in subscriptions:
                if await self._deliver_one(client, subscription, payload, private_key, subject):
                    delivered += 1
        return delivered

    async def _deliver_one(
        self,
        client: httpx.AsyncClient,
        subscription: WebPushSubscription,
        payload: bytes,
        private_key: ec.EllipticCurvePrivateKey,
        subject: str,
    ) -> bool:
        try:
            body = protocol.encrypt_payload(payload, subscription.p256dh, subscription.auth)
            headers = {
                'TTL': str(self.TTL_SECONDS),
                'Content-Encoding': 'aes128gcm',
                'Content-Type': 'application/octet-stream',
                'Urgency': self.URGENCY,
                'Authorization': protocol.vapid_authorization(
                    subscription.endpoint, private_key, subject
                ),
            }
        except ValueError as exc:
            # Stored keys the protocol layer rejects can never succeed — prune.
            logger.warning('pruning web push subscription %s (bad keys: %s)', subscription.id, exc)
            await self.repository.delete(subscription)
            return False

        try:
            response = await client.post(subscription.endpoint, content=body, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning('web push delivery to subscription %s failed: %s', subscription.id, exc)
            return False

        if response.status_code in (404, 410):
            # The push service says this subscription no longer exists.
            logger.info('pruning expired web push subscription %s (HTTP %s)',
                        subscription.id, response.status_code)
            await self.repository.delete(subscription)
            return False
        if response.status_code >= 300:
            logger.warning('web push delivery to subscription %s got HTTP %s: %s',
                           subscription.id, response.status_code, response.text[:200])
            return False
        await self.repository.touch_last_used(subscription)
        return True
