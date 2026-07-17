"""
Webhook Repository - Data Access Layer

Handles database operations for outbound webhook configurations.
"""

from typing import List

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import scoped
from models import Webhook


class WebhookRepository(TenantScopedRepository[Webhook]):
    """Repository for Webhook data access."""

    model = Webhook

    async def list_all(self) -> List[Webhook]:
        return await scoped(Webhook.all()).order_by('name')

    async def list_active(self) -> List[Webhook]:
        """Enabled webhooks, used to match an event against its subscribers."""
        return await scoped(Webhook.filter(is_active=True)).all()
