"""
Match Acknowledgment Repository - Data Access Layer

Handles all database operations for MatchAcknowledgment model.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from application.repositories._tenant import current_tenant_id, scoped
from models import Match, MatchAcknowledgment, User


class MatchAcknowledgmentRepository:
    """Repository for match acknowledgment data access."""

    @staticmethod
    async def list_for_match(match: Match) -> List[MatchAcknowledgment]:
        return await scoped(MatchAcknowledgment.filter(match=match)).prefetch_related('user')

    @staticmethod
    async def list_for_matches(match_ids: List[int]) -> Dict[int, List[MatchAcknowledgment]]:
        if not match_ids:
            return {}
        rows = await scoped(MatchAcknowledgment.filter(match_id__in=match_ids)).prefetch_related('user')
        result: Dict[int, List[MatchAcknowledgment]] = {mid: [] for mid in match_ids}
        for row in rows:
            result.setdefault(row.match_id, []).append(row)
        return result

    @staticmethod
    async def get(match: Match, user: User) -> Optional[MatchAcknowledgment]:
        return await MatchAcknowledgment.get_or_none(match=match, user=user, tenant_id=current_tenant_id())

    @staticmethod
    async def upsert(
        match: Match,
        user: User,
        *,
        acknowledged: bool,
        auto: bool,
    ) -> MatchAcknowledgment:
        acknowledged_at = datetime.now(timezone.utc) if acknowledged else None
        ack, _ = await MatchAcknowledgment.update_or_create(
            tenant_id=current_tenant_id(),
            match=match,
            user=user,
            defaults={
                'acknowledged_at': acknowledged_at,
                'auto_acknowledged': auto if acknowledged else False,
            },
        )
        return ack

    @staticmethod
    async def delete_for_match(match: Match) -> int:
        return await scoped(MatchAcknowledgment.filter(match=match)).delete()

    @staticmethod
    async def delete_for_user(match: Match, user: User) -> None:
        await scoped(MatchAcknowledgment.filter(match=match, user=user)).delete()
