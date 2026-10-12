"""
Community Event Repository - Data Access Layer

Member-submitted community events and the subscriptions that remind people
before one starts.
"""

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set

from tortoise.functions import Count

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import current_tenant_id, scoped
from models import (
    CommunityEvent,
    CommunityEventStatus,
    CommunityEventSubscription,
    User,
)


class CommunityEventRepository(TenantScopedRepository[CommunityEvent]):
    """Repository for community events."""

    model = CommunityEvent

    @staticmethod
    async def get_by_id(obj_id: int) -> Optional[CommunityEvent]:
        return await CommunityEvent.get_or_none(
            id=obj_id, tenant_id=current_tenant_id(),
        ).prefetch_related('host', 'reviewed_by')

    @staticmethod
    async def list_by_status(
        statuses: Iterable[CommunityEventStatus],
        starts_after: Optional[datetime] = None,
    ) -> List[CommunityEvent]:
        """Events in any of ``statuses``, soonest first."""
        query = CommunityEvent.filter(status__in=list(statuses))
        if starts_after is not None:
            query = query.filter(starts_at__gte=starts_after)
        return await scoped(query).order_by('starts_at', 'id').prefetch_related('host')

    @staticmethod
    async def list_for_host(host: User) -> List[CommunityEvent]:
        return await scoped(
            CommunityEvent.filter(host_id=host.id)
        ).order_by('-starts_at', '-id').prefetch_related('host')

    @staticmethod
    async def count_by_status(status: CommunityEventStatus) -> int:
        return await scoped(CommunityEvent.filter(status=status)).count()


class CommunityEventSubscriptionRepository(TenantScopedRepository[CommunityEventSubscription]):
    """Repository for community event subscriptions."""

    model = CommunityEventSubscription

    @staticmethod
    async def get_for(event_id: int, user_id: int) -> Optional[CommunityEventSubscription]:
        return await CommunityEventSubscription.get_or_none(
            event_id=event_id, user_id=user_id, tenant_id=current_tenant_id(),
        )

    @staticmethod
    async def event_ids_for_user(user_id: int, event_ids: Iterable[int]) -> Set[int]:
        rows = await scoped(
            CommunityEventSubscription.filter(user_id=user_id, event_id__in=list(event_ids))
        ).values_list('event_id', flat=True)
        return set(rows)  # type: ignore[arg-type]

    @staticmethod
    async def counts_for(event_ids: Iterable[int]) -> Dict[int, int]:
        rows = await (
            scoped(CommunityEventSubscription.filter(event_id__in=list(event_ids)))
            .annotate(n=Count('id'))
            .group_by('event_id')
            .values('event_id', 'n')
        )
        return {row['event_id']: row['n'] for row in rows}

    @staticmethod
    async def list_for_event(event_id: int) -> List[CommunityEventSubscription]:
        return await scoped(
            CommunityEventSubscription.filter(event_id=event_id)
        ).prefetch_related('user')

    @staticmethod
    async def clear_reminders(event_id: int) -> None:
        await scoped(
            CommunityEventSubscription.filter(event_id=event_id)
        ).update(reminder_sent_at=None)

    @staticmethod
    async def mark_reminded(subscription: CommunityEventSubscription, when: datetime) -> None:
        subscription.reminder_sent_at = when
        await subscription.save(update_fields=['reminder_sent_at'])

    @staticmethod
    async def due_for_reminder(
        window_start: datetime, window_end: datetime,
    ) -> List[CommunityEventSubscription]:
        """Un-reminded subscriptions to approved events starting in the window.

        Deliberately cross-tenant: the reminder loop scans every tenant and binds
        each row's own tenant scope before acting on it. Do NOT scope this.
        """
        return await CommunityEventSubscription.filter(
            reminder_sent_at__isnull=True,
            event__status=CommunityEventStatus.APPROVED,
            event__starts_at__gte=window_start,
            event__starts_at__lte=window_end,
        ).prefetch_related('event', 'user')
