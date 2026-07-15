"""
User Repository - Data Access Layer

Handles database operations for users.
"""

from typing import List, Optional

from tortoise.expressions import Q

from models import SYSTEM_USER_DISCORD_ID, Role, User


class UserRepository:
    """Repository for user data access."""

    @staticmethod
    async def get_by_id(user_id: int) -> Optional[User]:
        return await User.get_or_none(id=user_id)

    @staticmethod
    async def get_by_ids(user_ids: List[int]) -> dict[int, User]:
        """Resolve many users in a single query, keyed by id.

        Callers that need to validate a list of referenced user ids should use
        this instead of a per-id ``get_by_id`` loop (one round-trip, not N).
        """
        if not user_ids:
            return {}
        rows = await User.filter(id__in=list(set(user_ids)))
        return {u.id: u for u in rows}

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
            Q(username__icontains=search_term)
            | Q(display_name__icontains=search_term)
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
    async def get_or_create_by_discord_id(
        discord_id: int,
        username: str,
    ) -> tuple[User, bool]:
        return await User.get_or_create(
            discord_id=discord_id,
            defaults={'username': username},
        )

    @staticmethod
    async def get_or_create_system_user() -> User:
        """Return the reserved system :class:`User`, creating it if absent.

        Idempotent: keyed on the ``SYSTEM_USER_DISCORD_ID`` sentinel so repeated
        calls (and the migration seed) converge on one global row. The row is
        deliberately inactive for login purposes but is a valid audit actor.
        """
        user, _ = await User.get_or_create(
            discord_id=SYSTEM_USER_DISCORD_ID,
            defaults={
                'username': 'System',
                'is_system': True,
                'is_active': False,
                'dm_notifications': False,
            },
        )
        return user

    @staticmethod
    async def get_by_username(username: str) -> Optional[User]:
        """Exact (case-insensitive) username match — global, for SG ETL resolution.

        SG supplies a ``discordTag`` (the account's handle) but not always a
        discord id; this resolves that handle to an existing real ``User`` before
        falling back to a placeholder. Cross-tenant on purpose (``User`` is
        global). Returns the first match; ``username`` is not unique, so this is a
        best-effort resolution step, not an identity guarantee.
        """
        return await User.filter(username__iexact=username).exclude(is_placeholder=True).first()

    @staticmethod
    async def get_placeholder_by_speedgaming_id(speedgaming_id: str) -> Optional[User]:
        """Find an existing placeholder previously created for this SG player."""
        return await User.get_or_none(speedgaming_id=speedgaming_id)

    @staticmethod
    async def create_placeholder(
        speedgaming_id: str,
        username: str,
        display_name: Optional[str] = None,
    ) -> User:
        """Create a placeholder ``User`` for an unresolved SG player.

        ``discord_id`` is NULL (allowed only because ``is_placeholder`` is True —
        the DB CHECK enforces that pairing). The row is inactive for login but is
        a valid ``MatchPlayers.user``, so an unmatched SG entrant still shows on
        the roster. Upgraded in place by :meth:`upgrade_placeholder` when a
        discord id later appears.
        """
        return await User.create(
            username=username,
            display_name=display_name,
            discord_id=None,
            is_placeholder=True,
            speedgaming_id=speedgaming_id,
            is_active=False,
            dm_notifications=False,
        )

    @staticmethod
    async def upgrade_placeholder(
        user: User,
        discord_id: int,
        username: Optional[str] = None,
    ) -> User:
        """Promote a placeholder to a real ``User`` once its discord id appears."""
        user.discord_id = discord_id
        user.is_placeholder = False
        user.is_active = True
        if username:
            user.username = username
        await user.save()
        return user

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
