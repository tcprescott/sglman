"""
Crew Service - Business Logic Layer

Handles crew (commentator and tracker) related operations.
"""

from typing import Union, Optional

from models import Commentator, Tracker
from application.repositories import CommentatorRepository, TrackerRepository


class CrewService:
    """Service for crew-related business operations."""
    
    def __init__(self):
        self.commentator_repository = CommentatorRepository()
        self.tracker_repository = TrackerRepository()
    
    async def get_crew_member_by_id(
        self,
        crew_id: int,
        crew_type: str
    ) -> Optional[Union[Commentator, Tracker]]:
        """
        Get a crew member by ID and type.
        
        Args:
            crew_id: The crew member ID
            crew_type: 'commentator' or 'tracker'
            
        Returns:
            Commentator or Tracker object, or None if not found
            
        Raises:
            ValueError: If crew_type is invalid
        """
        if crew_type == 'commentator':
            return await self.commentator_repository.get_by_id(crew_id)
        elif crew_type == 'tracker':
            return await self.tracker_repository.get_by_id(crew_id)
        else:
            raise ValueError(f"Invalid crew_type: {crew_type}. Must be 'commentator' or 'tracker'")
    
    async def update_crew_approval(
        self,
        crew_member: Union[Commentator, Tracker],
        crew_type: str,
        approved: bool
    ) -> Union[Commentator, Tracker]:
        """
        Update the approval status of a crew member.
        
        Args:
            crew_member: The crew member to update
            crew_type: 'commentator' or 'tracker'
            approved: New approval status
            
        Returns:
            Updated crew member
            
        Raises:
            ValueError: If crew_type is invalid
        """
        if crew_type == 'commentator':
            return await self.commentator_repository.update(crew_member, approved=approved)
        elif crew_type == 'tracker':
            return await self.tracker_repository.update(crew_member, approved=approved)
        else:
            raise ValueError(f"Invalid crew_type: {crew_type}. Must be 'commentator' or 'tracker'")
    
    async def approve_crew_member(
        self,
        crew_member: Union[Commentator, Tracker],
        crew_type: str
    ) -> Union[Commentator, Tracker]:
        """
        Approve a crew member.
        
        Args:
            crew_member: The crew member to approve
            crew_type: 'commentator' or 'tracker'
            
        Returns:
            Approved crew member
            
        Raises:
            ValueError: If crew_type is invalid
        """
        if crew_type == 'commentator':
            return await self.commentator_repository.approve(crew_member)
        elif crew_type == 'tracker':
            return await self.tracker_repository.approve(crew_member)
        else:
            raise ValueError(f"Invalid crew_type: {crew_type}. Must be 'commentator' or 'tracker'")
