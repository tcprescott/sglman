"""
Match Comment Repository - Data Access Layer

Handles all database operations for the MatchComment model.
"""

from datetime import datetime
from typing import Dict, Iterable, List, Optional

from application.repositories._base import TenantScopedRepository
from application.repositories._tenant import scoped
from models import MatchComment, MatchCommentKind


class MatchCommentRepository(TenantScopedRepository[MatchComment]):
    """Repository for match comment data access."""

    model = MatchComment

    @staticmethod
    async def list_for_match(
        match_id: int, kinds: Optional[Iterable[MatchCommentKind]] = None,
    ) -> List[MatchComment]:
        query = MatchComment.filter(match_id=match_id)
        if kinds is not None:
            query = query.filter(kind__in=list(kinds))
        return await scoped(query).prefetch_related('author').order_by('created_at', 'id')

    @staticmethod
    async def count_by_author_since(match_id: int, author_id: int, since: datetime) -> int:
        return await scoped(
            MatchComment.filter(match_id=match_id, author_id=author_id, created_at__gte=since)
        ).count()

    @staticmethod
    async def counts_by_match(match_ids: List[int]) -> Dict[int, Dict[str, int]]:
        """``{match_id: {kind: count}}`` for a whole board in one query.

        Empty ``match_ids`` short-circuits rather than counting the tenant's
        entire history.
        """
        if not match_ids:
            return {}
        rows = await scoped(
            MatchComment.filter(match_id__in=match_ids)
        ).values_list('match_id', 'kind')
        counts: Dict[int, Dict[str, int]] = {}
        for match_id, kind in rows:
            key = kind.value if isinstance(kind, MatchCommentKind) else str(kind)
            per_match = counts.setdefault(match_id, {})
            per_match[key] = per_match.get(key, 0) + 1
        return counts
