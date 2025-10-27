"""
User Service - Business Logic Layer

Coordinates user-related operations and enforces business rules.
"""

from typing import Optional

from models import User
from application.repositories.user_repository import UserRepository


class UserService:
    """Service for user-related business operations."""
    
    def __init__(self):
        self.repository = UserRepository()
    
    async def get_user_by_discord_id(self, discord_id: str) -> Optional[User]:
        """
        Get a user by their Discord ID.
        
        Args:
            discord_id: Discord ID to look up
            
        Returns:
            User object or None if not found
        """
        return await self.repository.get_by_discord_id(discord_id)
    
    async def get_current_user_from_storage(self, storage_discord_id: Optional[str]) -> Optional[User]:
        """
        Get the current user from app.storage discord_id.
        
        Args:
            storage_discord_id: Discord ID from app.storage.user
            
        Returns:
            User object or None if not logged in or not found
        """
        if not storage_discord_id:
            return None
        
        return await self.repository.get_by_discord_id(storage_discord_id)
