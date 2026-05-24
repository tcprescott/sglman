"""
Audit Repository - Data Access Layer

Filtered/paginated queries over AuditLog.
"""

from datetime import datetime
from typing import List, Optional

from models import AuditLog


class AuditRepository:
    """Repository for AuditLog data access."""

    @staticmethod
    async def list(
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        user_id: Optional[int] = None,
        action_contains: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditLog]:
        query = AuditLog.all()
        if start is not None:
            query = query.filter(created_at__gte=start)
        if end is not None:
            query = query.filter(created_at__lte=end)
        if user_id is not None:
            query = query.filter(user_id=user_id)
        if action_contains:
            query = query.filter(action__icontains=action_contains)
        query = query.order_by('-created_at').offset(offset).limit(limit)
        return await query.prefetch_related('user')

    @staticmethod
    async def count(
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        user_id: Optional[int] = None,
        action_contains: Optional[str] = None,
    ) -> int:
        query = AuditLog.all()
        if start is not None:
            query = query.filter(created_at__gte=start)
        if end is not None:
            query = query.filter(created_at__lte=end)
        if user_id is not None:
            query = query.filter(user_id=user_id)
        if action_contains:
            query = query.filter(action__icontains=action_contains)
        return await query.count()
