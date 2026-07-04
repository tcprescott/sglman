"""
Webhook Service - Business Logic Layer

Staff-managed outbound webhooks: CRUD (all staff-gated and audited) plus the
delivery path that subscribes to the event bus and POSTs a signed JSON payload
to each subscribed endpoint.

Delivery is signed with HMAC-SHA256 over ``"{timestamp}.{body}"`` using the
per-webhook secret (GitHub-style ``sha256=`` header); the signed timestamp lets a
receiver reject replays. The secret is never returned by list/GET nor written to
logs.
"""

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
from urllib.parse import urlparse

import httpx

from application.events import Event, EventType, dispatch_queue
from application.repositories import WebhookDeliveryRepository, WebhookRepository
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.utils.environment import is_production
from models import User, Webhook, WebhookDelivery

logger = logging.getLogger(__name__)


class WebhookService:
    """CRUD + delivery for staff-managed outbound webhooks."""

    MAX_ATTEMPTS = 3
    DELIVERY_TIMEOUT = 10.0
    RETRY_BACKOFF_BASE = 2

    def __init__(self) -> None:
        self.repository = WebhookRepository()
        self.delivery_repository = WebhookDeliveryRepository()
        self.audit_service = AuditService()

    # ------------------------------------------------------------------ CRUD

    async def list_webhooks(self, actor: User) -> List[Webhook]:
        await AuthService.ensure(await AuthService.is_staff(actor), "Only Staff can view webhooks")
        return await self.repository.list_all()

    async def get_webhook(self, actor: User, webhook_id: int) -> Webhook:
        await AuthService.ensure(await AuthService.is_staff(actor), "Only Staff can view webhooks")
        return await self._require(webhook_id)

    async def create_webhook(
        self,
        actor: User,
        *,
        name: str,
        url: str,
        event_types: List[str],
        is_active: bool = True,
    ) -> Webhook:
        await AuthService.ensure(await AuthService.is_staff(actor), "Only Staff can create webhooks")
        name = (name or '').strip()
        if not name:
            raise ValueError("Webhook name is required")
        await self._validate_url(url)
        self._validate_event_types(event_types)
        webhook = await self.repository.create(
            name=name,
            url=url.strip(),
            secret=secrets.token_urlsafe(32),
            event_types=list(event_types),
            is_active=is_active,
        )
        await self.audit_service.write_log(
            actor,
            AuditActions.WEBHOOK_CREATED,
            {'webhook_id': webhook.id, 'name': name, 'url': webhook.url, 'event_types': list(event_types)},
        )
        return webhook

    async def update_webhook(
        self,
        actor: User,
        webhook_id: int,
        *,
        name: Optional[str] = None,
        url: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        is_active: Optional[bool] = None,
    ) -> Webhook:
        await AuthService.ensure(await AuthService.is_staff(actor), "Only Staff can modify webhooks")
        webhook = await self._require(webhook_id)
        changes: dict[str, Any] = {}
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("Webhook name is required")
            changes['name'] = name
        if url is not None:
            await self._validate_url(url)
            changes['url'] = url.strip()
        if event_types is not None:
            self._validate_event_types(event_types)
            changes['event_types'] = list(event_types)
        if is_active is not None:
            changes['is_active'] = is_active
        if changes:
            webhook = await self.repository.update(webhook, **changes)
            await self.audit_service.write_log(
                actor,
                AuditActions.WEBHOOK_UPDATED,
                {'webhook_id': webhook.id, 'changes': {k: v for k, v in changes.items()}},
            )
        return webhook

    async def delete_webhook(self, actor: User, webhook_id: int) -> None:
        await AuthService.ensure(await AuthService.is_staff(actor), "Only Staff can delete webhooks")
        webhook = await self._require(webhook_id)
        await self.audit_service.write_log(
            actor,
            AuditActions.WEBHOOK_DELETED,
            {'webhook_id': webhook.id, 'name': webhook.name},
        )
        await self.repository.delete(webhook)

    async def regenerate_secret(self, actor: User, webhook_id: int) -> str:
        await AuthService.ensure(await AuthService.is_staff(actor), "Only Staff can rotate webhook secrets")
        webhook = await self._require(webhook_id)
        new_secret = secrets.token_urlsafe(32)
        await self.repository.update(webhook, secret=new_secret)
        await self.audit_service.write_log(
            actor,
            AuditActions.WEBHOOK_SECRET_REGENERATED,
            {'webhook_id': webhook.id},
        )
        return new_secret

    async def list_deliveries(
        self, actor: User, webhook_id: int, limit: int = 50, offset: int = 0
    ) -> List[WebhookDelivery]:
        await AuthService.ensure(await AuthService.is_staff(actor), "Only Staff can view webhook deliveries")
        webhook = await self._require(webhook_id)
        return await self.delivery_repository.list_for_webhook(webhook, limit=limit, offset=offset)

    # ------------------------------------------------------------- delivery

    async def deliver_event(self, event: Event) -> None:
        """Event-bus subscriber: enqueue a POST to every webhook that wants this event."""
        for webhook in await self.repository.list_active():
            subscribed = webhook.event_types or []
            if EventType.WILDCARD in subscribed or event.event_type in subscribed:
                dispatch_queue.enqueue(self._deliver_one(webhook, event))

    async def _deliver_one(self, webhook: Webhook, event: Event) -> None:
        body = json.dumps(event.to_wire(), default=str, sort_keys=True)
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        signature = hmac.new(
            webhook.secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256
        ).hexdigest()
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'sglman-webhook',
            'X-SGL-Event': event.event_type,
            'X-SGL-Delivery': str(uuid.uuid4()),
            'X-SGL-Timestamp': timestamp,
            'X-SGL-Signature': f'sha256={signature}',
        }
        status: Optional[int] = None
        error: Optional[str] = None
        success = False
        attempts = 0
        async with httpx.AsyncClient(timeout=self.DELIVERY_TIMEOUT) as client:
            for attempt in range(self.MAX_ATTEMPTS):
                attempts = attempt + 1
                try:
                    response = await client.post(webhook.url, content=body, headers=headers)
                    status = response.status_code
                    if 200 <= status < 300:
                        success = True
                        break
                    error = f"HTTP {status}"
                except httpx.HTTPError as exc:
                    error = str(exc)
                if attempt < self.MAX_ATTEMPTS - 1:
                    await asyncio.sleep(self.RETRY_BACKOFF_BASE ** attempt)
        await self.delivery_repository.create(
            webhook=webhook,
            event_type=event.event_type,
            payload=body,
            response_status=status,
            attempt_count=attempts,
            success=success,
            error=None if success else error,
            delivered_at=datetime.now(timezone.utc) if success else None,
        )

    # ------------------------------------------------------------ internals

    async def _require(self, webhook_id: int) -> Webhook:
        webhook = await self.repository.get_by_id(webhook_id)
        if webhook is None:
            raise ValueError("Webhook not found")
        return webhook

    def _validate_event_types(self, event_types: List[str]) -> None:
        if not event_types:
            raise ValueError("Select at least one event type")
        invalid = [t for t in event_types if not EventType.is_valid(t)]
        if invalid:
            raise ValueError(f"Unknown event type(s): {', '.join(invalid)}")

    async def _validate_url(self, url: str) -> None:
        parsed = urlparse((url or '').strip())
        allow_http = not is_production()
        if parsed.scheme != 'https' and not (allow_http and parsed.scheme == 'http'):
            raise ValueError("Webhook URL must use https://")
        if not parsed.hostname:
            raise ValueError("Webhook URL must include a host")
        # Block internal targets (SSRF). Skipped outside production so a dev can
        # point a webhook at a localhost receiver.
        if is_production():
            await self._ensure_public_host(parsed.hostname)

    async def _ensure_public_host(self, hostname: str) -> None:
        try:
            infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
        except socket.gaierror as exc:
            raise ValueError(f"Could not resolve webhook host '{hostname}'") from exc
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                raise ValueError("Webhook URL must point to a public address")
