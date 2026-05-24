"""
Match Watcher Repository - Data Access Layer

Handles all database operations for MatchWatcher model.
"""

from typing import List, Optional, Tuple

from models import Match, MatchWatcher, User


class MatchWatcherRepository:
    """Repository for match watcher data access."""

    @staticmethod
    async def get_by_id(watcher_id: int) -> Optional[MatchWatcher]:
        return await MatchWatcher.get_or_none(id=watcher_id)

    @staticmethod
    async def get_by_match(match: Match) -> List[MatchWatcher]:
        return await MatchWatcher.filter(match=match).prefetch_related('user')

    @staticmethod
    async def get_by_match_and_user(match: Match, user: User) -> Optional[MatchWatcher]:
        return await MatchWatcher.get_or_none(match=match, user=user)

    @staticmethod
    async def get_by_user(user: User) -> List[MatchWatcher]:
        return await MatchWatcher.filter(user=user)

    @staticmethod
    async def get_match_ids_for_user(user: User) -> List[int]:
        rows = await MatchWatcher.filter(user=user).values_list('match_id', flat=True)
        return list(rows)

    @staticmethod
    async def is_watching(match_id: int, user_id: int) -> bool:
        return await MatchWatcher.filter(match_id=match_id, user_id=user_id).exists()

    @staticmethod
    async def get_or_create(match: Match, user: User) -> Tuple[MatchWatcher, bool]:
        return await MatchWatcher.get_or_create(match=match, user=user)

    @staticmethod
    async def delete(watcher: MatchWatcher) -> None:
        await watcher.delete()

    @staticmethod
    async def delete_by_match_and_user(match: Match, user: User) -> bool:
        deleted = await MatchWatcher.filter(match=match, user=user).delete()
        return bool(deleted)
