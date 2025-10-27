"""
Tracker Repository - Data Access Layer

Handles all database operations for Tracker model.
"""

from typing import List, Optional

from models import Tracker, User, Match


class TrackerRepository:
    """Repository for tracker-related data access."""
    
    @staticmethod
    async def get_by_id(tracker_id: int) -> Optional[Tracker]:
        """Get a tracker by ID."""
        return await Tracker.get_or_none(id=tracker_id)
    
    @staticmethod
    async def get_by_match(match: Match) -> List[Tracker]:
        """Get all trackers for a match."""
        return await Tracker.filter(match=match).prefetch_related('user')
    
    @staticmethod
    async def get_by_match_and_user(match: Match, user: User) -> Optional[Tracker]:
        """Get a specific tracker entry for a match and user."""
        return await Tracker.get_or_none(match=match, user=user)
    
    @staticmethod
    async def create(match: Match, user: User, approved: bool = False) -> Tracker:
        """Create a new tracker entry."""
        return await Tracker.create(match=match, user=user, approved=approved)
    
    @staticmethod
    async def update(tracker: Tracker, **fields) -> Tracker:
        """Update a tracker entry."""
        await tracker.update_from_dict(fields)
        await tracker.save()
        return tracker
    
    @staticmethod
    async def delete(tracker: Tracker) -> None:
        """Delete a tracker entry."""
        await tracker.delete()
    
    @staticmethod
    async def approve(tracker: Tracker) -> Tracker:
        """Approve a tracker."""
        return await TrackerRepository.update(tracker, approved=True)
