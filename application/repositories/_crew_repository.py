"""
Crew Repository - shared Data Access Layer for crew-signup models.

Commentator and Tracker have identical persistence shapes, so the actual CRUD
lives here and the concrete repositories only bind the model class.
"""

from datetime import datetime, timezone
from typing import Generic, List, Optional, Type, TypeVar

from tortoise.models import Model

from application.repositories._tenant import current_tenant_id, scoped
from models import Match, User

T = TypeVar("T", bound=Model)


class CrewRepository(Generic[T]):
    """Generic data access for a crew-signup model (Commentator/Tracker).

    Subclasses set ``model`` to the concrete Tortoise model.
    """

    model: Type[T]

    @classmethod
    async def get_by_id(cls, crew_id: int) -> Optional[T]:
        """Get a crew entry by ID."""
        return await cls.model.get_or_none(id=crew_id, tenant_id=current_tenant_id())

    @classmethod
    async def get_by_match(cls, match: Match) -> List[T]:
        """Get all crew entries for a match."""
        return await scoped(cls.model.filter(match=match)).prefetch_related('user')

    @classmethod
    async def get_by_match_and_user(cls, match: Match, user: User) -> Optional[T]:
        """Get a specific crew entry for a match and user."""
        return await cls.model.get_or_none(match=match, user=user, tenant_id=current_tenant_id())

    @classmethod
    async def get_for_user(cls, user: User, since: Optional[datetime] = None) -> List[T]:
        """This person's own crew commitments, soonest first.

        The query behind My Crew. Nothing anywhere listed a volunteer's own
        signups: after signing up, their only handle on the commitment was a
        Withdraw button in one row of a shared, chronologically-sorted board.
        ``since`` drops matches that finished before it, so the page can default
        to what is still ahead.
        """
        query = scoped(cls.model.filter(user=user))
        if since is not None:
            query = query.filter(match__scheduled_at__gte=since)
        return await query.prefetch_related(
            'match', 'match__tournament', 'match__stage',
            'match__players', 'match__players__user',
        ).order_by('match__scheduled_at')

    @classmethod
    async def create(cls, match: Match, user: User, approved: bool = False) -> T:
        """Create a new crew entry."""
        return await cls.model.create(tenant_id=current_tenant_id(), match=match, user=user, approved=approved)

    @classmethod
    async def update(cls, crew_member: T, **fields) -> T:
        """Update a crew entry."""
        await crew_member.update_from_dict(fields)
        await crew_member.save()
        return crew_member

    @classmethod
    async def delete(cls, crew_member: T) -> None:
        """Delete a crew entry."""
        await crew_member.delete()

    @classmethod
    async def approve(cls, crew_member: T) -> T:
        """Approve a crew entry."""
        return await cls.update(crew_member, approved=True)

    @classmethod
    async def acknowledge(cls, crew_member: T) -> T:
        """Mark a crew assignment as acknowledged by the crew member."""
        return await cls.update(crew_member, acknowledged_at=datetime.now(timezone.utc))

    @classmethod
    async def clear_acknowledgment(cls, crew_member: T) -> T:
        """Reset acknowledgment fields on a crew assignment."""
        return await cls.update(crew_member, acknowledged_at=None)
