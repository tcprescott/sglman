"""
User Repository - Data Access Layer

Handles database operations for users.
"""

from typing import List, Optional

from models import Role, User


class UserRepository:
    """Repository for user data access."""

    @staticmethod
    async def get_by_id(user_id: int) -> Optional[User]:
        return await User.get_or_none(id=user_id)

    @staticmethod
    async def get_by_discord_id(discord_id: str) -> Optional[User]:
        return await User.get_or_none(discord_id=discord_id)

    @staticmethod
    async def get_all(
        role: Optional[Role] = None,
        has_discord: bool = False,
    ) -> List[User]:
        """
        Get all users with optional filters.

        Args:
            role: Filter to users holding this role (via the userrole table).
            has_discord: Only return users with Discord IDs.
        """
        query = User.all().order_by('username')

        if role is not None:
            query = query.filter(roles__role=role).distinct()

        if has_discord:
            query = query.exclude(discord_id=None)

        return await query

    @staticmethod
    async def search_by_name(
        search_term: str,
        limit: int = 20,
    ) -> List[User]:
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
    ) -> User:
        return await User.create(
            username=username,
            discord_id=discord_id,
            display_name=display_name,
            pronouns=pronouns,
            is_active=is_active,
        )

    @staticmethod
    async def update(user: User, **fields) -> None:
        for key, value in fields.items():
            setattr(user, key, value)
        await user.save()

    @staticmethod
    async def delete(user: User) -> None:
        await user.delete()

    @staticmethod
    async def update_discord_info(
        user: User,
        username: str,
        discriminator: Optional[str] = None,
        avatar: Optional[str] = None,
    ) -> None:
        user.username = username
        if discriminator is not None:
            user.discriminator = discriminator
        if avatar is not None:
            user.avatar = avatar
        await user.save()
