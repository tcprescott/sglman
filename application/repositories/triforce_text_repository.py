"""
Triforce Text Repository - Data Access Layer

Handles all database operations for the TriforceText model.
"""

from datetime import datetime
from typing import List, Optional

from models import Tournament, TriforceText, User


class TriforceTextRepository:
    """Repository for triforce text data access."""

    _UNSET = object()

    @staticmethod
    async def get_by_id(text_id: int) -> Optional[TriforceText]:
        return await TriforceText.get_or_none(id=text_id).prefetch_related(
            'tournament', 'user', 'approved_by'
        )

    @staticmethod
    async def list_by_tournament(
        tournament: Tournament,
        approved=_UNSET,
    ) -> List[TriforceText]:
        """List texts for a tournament.

        ``approved`` may be left unset (all), ``None`` (pending), or
        ``True``/``False`` for decided rows.
        """
        query = TriforceText.filter(tournament=tournament)
        if approved is not TriforceTextRepository._UNSET:
            query = query.filter(approved=approved)
        return await query.order_by('-created_at').prefetch_related('user', 'approved_by')

    @staticmethod
    async def list_by_tournament_and_user(
        tournament: Tournament, user: User
    ) -> List[TriforceText]:
        return await TriforceText.filter(
            tournament=tournament, user=user
        ).order_by('-created_at')

    @staticmethod
    async def list_approved(tournament: Tournament) -> List[TriforceText]:
        return await TriforceText.filter(tournament=tournament, approved=True)

    @staticmethod
    async def list_approved_user_ids(tournament: Tournament) -> List[int]:
        rows = await TriforceText.filter(
            tournament=tournament, approved=True
        ).distinct().values_list('user_id', flat=True)
        return [uid for uid in rows if uid is not None]

    @staticmethod
    async def list_approved_by_user(
        tournament: Tournament, user_id: int
    ) -> List[TriforceText]:
        return await TriforceText.filter(
            tournament=tournament, approved=True, user_id=user_id
        )

    @staticmethod
    async def create(
        tournament: Tournament,
        user: Optional[User],
        text: str,
        author: Optional[str],
    ) -> TriforceText:
        return await TriforceText.create(
            tournament=tournament,
            user=user,
            text=text,
            author=author,
            approved=None,
        )

    @staticmethod
    async def update(triforce_text: TriforceText, **changes) -> TriforceText:
        await triforce_text.update_from_dict(changes)
        await triforce_text.save()
        return triforce_text

    @staticmethod
    async def set_moderation(
        triforce_text: TriforceText, approved: bool, actor: User
    ) -> TriforceText:
        return await TriforceTextRepository.update(
            triforce_text,
            approved=approved,
            approved_by=actor,
            approved_at=datetime.now(),
        )

    @staticmethod
    async def delete(triforce_text: TriforceText) -> None:
        await triforce_text.delete()
