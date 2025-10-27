"""
User Repository - Data Access Layer

Handles database operations for users.
"""

from typing import List, Optional

from models import User, Permissions


class UserRepository:
    """Repository for user data access."""
    
    @staticmethod
    async def get_by_id(user_id: int) -> Optional[User]:
        """
        Get a user by ID.
        
        Args:
            user_id: The user ID
            
        Returns:
            User object or None
        """
        return await User.get_or_none(id=user_id)
    
    @staticmethod
    async def get_by_discord_id(discord_id: str) -> Optional[User]:
        """
        Get a user by Discord ID.
        
        Args:
            discord_id: The Discord ID
            
        Returns:
            User object or None
        """
        return await User.get_or_none(discord_id=discord_id)
    
    @staticmethod
    async def get_all(
        permission_level: Optional[Permissions] = None,
        has_discord: bool = False
    ) -> List[User]:
        """
        Get all users with optional filters.
        
        Args:
            permission_level: Filter by minimum permission level
            has_discord: Only return users with Discord IDs
            
        Returns:
            List of User objects
        """
        query = User.all().order_by('username')
        
        if permission_level is not None:
            query = query.filter(permission__gte=permission_level)
        
        if has_discord:
            query = query.exclude(discord_id=None)
        
        return await query
    
    @staticmethod
    async def search_by_name(
        search_term: str,
        limit: int = 20
    ) -> List[User]:
        """
        Search users by name (username or preferred_name).
        
        Args:
            search_term: Search term to match
            limit: Maximum number of results
            
        Returns:
            List of matching User objects
        """
        return await User.filter(
            username__icontains=search_term
        ).limit(limit) | await User.filter(
            preferred_name__icontains=search_term
        ).limit(limit)
    
    @staticmethod
    async def create(
        username: str,
        discord_id: Optional[int] = None,
        display_name: Optional[str] = None,
        pronouns: Optional[str] = None,
        is_active: bool = True,
        permission: int = 0,
        access_token: Optional[str] = None
    ) -> User:
        """
        Create a new user.
        
        Args:
            username: Username
            discord_id: Discord ID
            display_name: Display name
            pronouns: User pronouns
            is_active: Whether user is active
            permission: Permission level (0=User, 1=Tournament Admin, 2=Superadmin)
            access_token: Discord access token
            
        Returns:
            Created User object
        """
        return await User.create(
            username=username,
            discord_id=discord_id,
            display_name=display_name,
            pronouns=pronouns,
            is_active=is_active,
            permission=permission,
            access_token=access_token
        )
    
    @staticmethod
    async def update(user: User, **fields) -> None:
        """
        Update user fields.
        
        Args:
            user: User to update
            **fields: Fields to update
        """
        for key, value in fields.items():
            setattr(user, key, value)
        await user.save()
    
    @staticmethod
    async def delete(user: User) -> None:
        """
        Delete a user.
        
        Args:
            user: User to delete
        """
        await user.delete()
    
    @staticmethod
    async def update_discord_info(
        user: User,
        username: str,
        discriminator: Optional[str] = None,
        avatar: Optional[str] = None
    ) -> None:
        """
        Update user's Discord information.
        
        Args:
            user: User to update
            username: New username
            discriminator: New discriminator
            avatar: New avatar URL
        """
        user.username = username
        if discriminator is not None:
            user.discriminator = discriminator
        if avatar is not None:
            user.avatar = avatar
        await user.save()
    
    @staticmethod
    async def set_permission(user: User, permission: Permissions) -> None:
        """
        Update user's permission level.
        
        Args:
            user: User to update
            permission: New permission level
        """
        user.permission = permission
        await user.save()
