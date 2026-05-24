"""
Commentator Repository - Data Access Layer

Handles all database operations for Commentator model.
"""

from datetime import datetime
from typing import List, Optional

from models import Commentator, User, Match


class CommentatorRepository:
    """Repository for commentator-related data access."""
    
    @staticmethod
    async def get_by_id(commentator_id: int) -> Optional[Commentator]:
        """Get a commentator by ID."""
        return await Commentator.get_or_none(id=commentator_id)
    
    @staticmethod
    async def get_by_match(match: Match) -> List[Commentator]:
        """Get all commentators for a match."""
        return await Commentator.filter(match=match).prefetch_related('user')
    
    @staticmethod
    async def get_by_match_and_user(match: Match, user: User) -> Optional[Commentator]:
        """Get a specific commentator entry for a match and user."""
        return await Commentator.get_or_none(match=match, user=user)
    
    @staticmethod
    async def create(match: Match, user: User, approved: bool = False) -> Commentator:
        """Create a new commentator entry."""
        return await Commentator.create(match=match, user=user, approved=approved)
    
    @staticmethod
    async def update(commentator: Commentator, **fields) -> Commentator:
        """Update a commentator entry."""
        await commentator.update_from_dict(fields)
        await commentator.save()
        return commentator
    
    @staticmethod
    async def delete(commentator: Commentator) -> None:
        """Delete a commentator entry."""
        await commentator.delete()
    
    @staticmethod
    async def approve(commentator: Commentator) -> Commentator:
        """Approve a commentator."""
        return await CommentatorRepository.update(commentator, approved=True)

    @staticmethod
    async def acknowledge(commentator: Commentator) -> Commentator:
        """Mark a commentator assignment as acknowledged by the crew member."""
        return await CommentatorRepository.update(
            commentator,
            acknowledged_at=datetime.now(),
        )

    @staticmethod
    async def clear_acknowledgment(commentator: Commentator) -> Commentator:
        """Reset acknowledgment fields on a commentator assignment."""
        return await CommentatorRepository.update(
            commentator,
            acknowledged_at=None,
        )
