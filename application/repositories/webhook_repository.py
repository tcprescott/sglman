"""
Webhook Repository - Data Access Layer

Handles database operations for outbound webhook configurations.
"""

from typing import Any, List, Optional

from models import Webhook


class WebhookRepository:
    """Repository for Webhook data access."""

    async def get_by_id(self, webhook_id: int) -> Optional[Webhook]:
        return await Webhook.get_or_none(id=webhook_id)

    async def list_all(self) -> List[Webhook]:
        return await Webhook.all().order_by('name')

    async def list_active(self) -> List[Webhook]:
        """Enabled webhooks, used to match an event against its subscribers."""
        return await Webhook.filter(is_active=True).all()

    async def create(self, **fields: Any) -> Webhook:
        return await Webhook.create(**fields)

    async def update(self, webhook: Webhook, **fields: Any) -> Webhook:
        for key, value in fields.items():
            setattr(webhook, key, value)
        await webhook.save()
        return webhook

    async def delete(self, webhook: Webhook) -> None:
        await webhook.delete()
