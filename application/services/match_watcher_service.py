"""
Match Watcher Service - Business Logic Layer

Lets logged-in users opt in to receive Discord DM updates for a match's
lifecycle transitions (seated, started, finished, confirmed) without
being a participant or crew member.
"""

from typing import List

from application.repositories import MatchRepository, MatchWatcherRepository
from application.services.audit_service import AuditService
from models import MatchWatcher, User


class MatchWatcherService:
    """Service for users watching matches for Discord notifications."""

    def __init__(self):
        self.repository = MatchWatcherRepository()
        self.match_repository = MatchRepository()
        self.audit_service = AuditService()

    async def watch(self, match_id: int, user: User) -> MatchWatcher:
        match = await self.match_repository.get_by_id(match_id, prefetch_relations=False)
        if not match:
            raise ValueError(f"Match {match_id} not found")
        if match.confirmed_at is not None:
            raise ValueError("Match is already confirmed; no further updates will be sent.")

        watcher, created = await self.repository.get_or_create(match=match, user=user)
        if created:
            await self.audit_service.write_log(
                user, f'Watched match {match_id}', '',
            )
        return watcher

    async def unwatch(self, match_id: int, user: User) -> bool:
        match = await self.match_repository.get_by_id(match_id, prefetch_relations=False)
        if not match:
            return False
        removed = await self.repository.delete_by_match_and_user(match=match, user=user)
        if removed:
            await self.audit_service.write_log(
                user, f'Unwatched match {match_id}', '',
            )
        return removed

    async def is_watching(self, match_id: int, user: User) -> bool:
        return await self.repository.is_watching(match_id, user.id)

    async def list_watched_match_ids(self, user: User) -> List[int]:
        return await self.repository.get_match_ids_for_user(user)
