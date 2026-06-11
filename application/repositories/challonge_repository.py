"""
Challonge Repository - Data Access Layer

Pure data access for the Challonge service-account connection, the bracket
mirror (participants + matches), and their links to sglman users/matches.
No business logic.
"""

from datetime import datetime
from typing import List, Optional

from tortoise.expressions import Q

from models import (
    ChallongeConnection,
    ChallongeMatch,
    ChallongeMatchState,
    ChallongeParticipant,
    Match,
    Tournament,
    User,
)


class ChallongeRepository:
    """Repository for Challonge connection and bracket-mirror data."""

    # ------------------------------------------------------------------
    # Service-account connection (single logical row; newest is authoritative)
    # ------------------------------------------------------------------
    @staticmethod
    async def get_connection() -> Optional[ChallongeConnection]:
        return await ChallongeConnection.all().order_by('-id').first()

    @staticmethod
    async def save_connection(
        access_token: str,
        refresh_token: Optional[str],
        token_expires_at: Optional[datetime],
        scopes: Optional[str],
        challonge_username: Optional[str],
        connected_by: Optional[User],
    ) -> ChallongeConnection:
        existing = await ChallongeRepository.get_connection()
        if existing:
            existing.access_token = access_token
            existing.refresh_token = refresh_token
            existing.token_expires_at = token_expires_at
            existing.scopes = scopes
            existing.challonge_username = challonge_username
            existing.connected_by = connected_by
            await existing.save()
            return existing
        return await ChallongeConnection.create(
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            scopes=scopes,
            challonge_username=challonge_username,
            connected_by=connected_by,
        )

    @staticmethod
    async def update_connection_tokens(
        connection: ChallongeConnection,
        access_token: str,
        refresh_token: Optional[str],
        token_expires_at: Optional[datetime],
    ) -> None:
        connection.access_token = access_token
        if refresh_token:
            connection.refresh_token = refresh_token
        connection.token_expires_at = token_expires_at
        await connection.save()

    @staticmethod
    async def clear_connection() -> int:
        return await ChallongeConnection.all().delete()

    # ------------------------------------------------------------------
    # Participants
    # ------------------------------------------------------------------
    @staticmethod
    async def upsert_participant(
        tournament: Tournament,
        challonge_participant_id: str,
        name: Optional[str],
        challonge_user_id: Optional[str],
        user: Optional[User],
    ) -> ChallongeParticipant:
        participant, _ = await ChallongeParticipant.get_or_create(
            tournament=tournament,
            challonge_participant_id=challonge_participant_id,
            defaults={'name': name, 'challonge_user_id': challonge_user_id, 'user': user},
        )
        participant.name = name
        participant.challonge_user_id = challonge_user_id
        participant.user = user
        await participant.save()
        return participant

    @staticmethod
    async def get_participant(
        tournament: Tournament, challonge_participant_id: str,
    ) -> Optional[ChallongeParticipant]:
        return await ChallongeParticipant.get_or_none(
            tournament=tournament, challonge_participant_id=challonge_participant_id,
        ).prefetch_related('user')

    @staticmethod
    async def list_participants(tournament: Tournament) -> List[ChallongeParticipant]:
        return await ChallongeParticipant.filter(tournament=tournament).prefetch_related('user')

    # ------------------------------------------------------------------
    # Matches
    # ------------------------------------------------------------------
    @staticmethod
    async def upsert_match(
        tournament: Tournament,
        challonge_match_id: str,
        round_: Optional[int],
        state: ChallongeMatchState,
        participant1: Optional[ChallongeParticipant],
        participant2: Optional[ChallongeParticipant],
        winner_participant: Optional[ChallongeParticipant],
    ) -> ChallongeMatch:
        match, _ = await ChallongeMatch.get_or_create(
            tournament=tournament,
            challonge_match_id=challonge_match_id,
            defaults={'round': round_, 'state': state},
        )
        match.round = round_
        match.state = state
        match.participant1 = participant1
        match.participant2 = participant2
        match.winner_participant = winner_participant
        await match.save()
        return match

    @staticmethod
    async def get_match(challonge_match_id_pk: int) -> Optional[ChallongeMatch]:
        return await ChallongeMatch.get_or_none(id=challonge_match_id_pk).prefetch_related(
            'tournament', 'participant1__user', 'participant2__user', 'match',
        )

    @staticmethod
    async def get_challonge_match_for_match(match: Match) -> Optional[ChallongeMatch]:
        return await ChallongeMatch.get_or_none(match=match).prefetch_related(
            'tournament', 'participant1__user', 'participant2__user',
        )

    @staticmethod
    async def link_match(challonge_match: ChallongeMatch, match: Match) -> None:
        challonge_match.match = match
        await challonge_match.save()

    @staticmethod
    async def unscheduled_open_matches_for_user(user: User) -> List[ChallongeMatch]:
        """Open bracket matches the user is in that aren't yet scheduled in sglman."""
        return await ChallongeMatch.filter(
            Q(participant1__user=user) | Q(participant2__user=user),
            state=ChallongeMatchState.OPEN,
            match_id__isnull=True,
        ).prefetch_related(
            'tournament', 'participant1__user', 'participant2__user',
        )
