"""
Audit Repository - Data Access Layer

Filtered/paginated queries over AuditLog.
"""

from datetime import datetime
from typing import List, Optional, Sequence

from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from application.repositories._tenant import scoped
from models import AuditLog


class AuditRepository:
    """Repository for AuditLog data access.

    Reads are scoped to the current tenant and raise without one (AuditLog.tenant
    is nullable, so an unscoped ``tenant_id=None`` filter would read the
    NULL-tenant platform rows instead of failing).
    """

    @staticmethod
    def _filtered(
        *,
        start: Optional[datetime],
        end: Optional[datetime],
        user_id: Optional[int],
        action_contains: Optional[str],
        action_prefixes: Optional[Sequence[str]],
        actions_in: Optional[Sequence[str]],
    ) -> QuerySet:
        query = scoped(AuditLog.all())
        if start is not None:
            query = query.filter(created_at__gte=start)
        if end is not None:
            query = query.filter(created_at__lte=end)
        if user_id is not None:
            query = query.filter(user_id=user_id)
        if action_prefixes is not None:
            area = Q(*[Q(action__startswith=p) for p in action_prefixes], join_type='OR') \
                if action_prefixes else Q(id__in=[])
            query = query.filter(area)
        if action_contains or actions_in:
            text = Q(action__icontains=action_contains) if action_contains else Q(id__in=[])
            if actions_in:
                text = text | Q(action__in=list(actions_in))
            query = query.filter(text)
        return query

    @staticmethod
    async def list(
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        user_id: Optional[int] = None,
        action_contains: Optional[str] = None,
        action_prefixes: Optional[Sequence[str]] = None,
        actions_in: Optional[Sequence[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditLog]:
        query = AuditRepository._filtered(
            start=start, end=end, user_id=user_id, action_contains=action_contains,
            action_prefixes=action_prefixes, actions_in=actions_in,
        )
        query = query.order_by('-created_at', '-id').offset(offset).limit(limit)
        return await query.prefetch_related('user')

    @staticmethod
    async def count(
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        user_id: Optional[int] = None,
        action_contains: Optional[str] = None,
        action_prefixes: Optional[Sequence[str]] = None,
        actions_in: Optional[Sequence[str]] = None,
    ) -> int:
        return await AuditRepository._filtered(
            start=start, end=end, user_id=user_id, action_contains=action_contains,
            action_prefixes=action_prefixes, actions_in=actions_in,
        ).count()
