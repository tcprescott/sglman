"""Watch Layout Repository - Data Access Layer

Each browser's seen/rated row per Watch page layout, in the current community.
"""

from typing import Dict, Optional

from models import WatchLayoutVote

from ._tenant import current_tenant_id, scoped


class WatchLayoutRepository:
    """Data access for :class:`WatchLayoutVote`."""

    @staticmethod
    async def mark_seen(session_id: str, layout: str) -> None:
        await WatchLayoutVote.get_or_create(
            tenant_id=current_tenant_id(), session_id=session_id, layout=layout,
        )

    @staticmethod
    async def set_vote(session_id: str, layout: str, vote: Optional[str]) -> None:
        row, _ = await WatchLayoutVote.get_or_create(
            tenant_id=current_tenant_id(), session_id=session_id, layout=layout,
        )
        row.vote = vote
        await row.save(update_fields=['vote', 'updated_at'])

    @staticmethod
    async def votes_for(session_id: str) -> Dict[str, Optional[str]]:
        rows = await scoped(WatchLayoutVote.filter(session_id=session_id)).values_list('layout', 'vote')
        return {str(layout): vote for layout, vote in rows}

    @staticmethod
    async def all_rows() -> list[tuple[str, Optional[str]]]:
        return [
            (str(layout), vote)
            for layout, vote in await scoped(WatchLayoutVote.all()).values_list('layout', 'vote')
        ]
