"""
Challonge Repository - Data Access Layer

Pure data access for the Challonge service-account connection, the bracket
mirror (participants + matches), and their links to sglman users/matches.
No business logic.
"""

from datetime import datetime, timezone
from typing import List, Optional, Set

from tortoise.expressions import Q

from application.repositories._tenant import current_tenant_id, scoped
from models import (
    ChallongeApiUsage,
    ChallongeConnection,
    ChallongeMatch,
    ChallongeMatchState,
    ChallongeParticipant,
    Match,
    Tournament,
    User,
)


class ChallongeRepository:
    """Repository for Challonge connection and bracket-mirror data.

    Every Challonge model is tenant-scoped: each tenant links its own service
    account, mirrors its own brackets, and tracks its own API quota. The
    connection is "newest row per tenant is authoritative"; usage is tallied per
    ``(tenant, period)``.
    """

    # ------------------------------------------------------------------
    # Service-account connection (newest row per tenant is authoritative)
    # ------------------------------------------------------------------
    @staticmethod
    async def get_connection() -> Optional[ChallongeConnection]:
        return await scoped(ChallongeConnection.all()).order_by('-id').first()

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
            tenant_id=current_tenant_id(),
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
        return await scoped(ChallongeConnection.all()).delete()

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
            tenant_id=current_tenant_id(),
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
    async def resolve_users_by_challonge_ids(challonge_user_ids: List[str]) -> dict:
        """Map ``challonge_user_id -> User`` for the linked ids, in one query.

        Lets bracket sync resolve every participant's sglman user up-front
        instead of a ``User.get_or_none`` round-trip per participant.
        """
        ids = [c for c in challonge_user_ids if c]
        if not ids:
            return {}
        rows = await User.filter(challonge_user_id__in=list(set(ids)))
        return {u.challonge_user_id: u for u in rows}

    @staticmethod
    async def get_participant(
        tournament: Tournament, challonge_participant_id: str,
    ) -> Optional[ChallongeParticipant]:
        return await ChallongeParticipant.get_or_none(
            tournament=tournament, challonge_participant_id=challonge_participant_id,
            tenant_id=current_tenant_id(),
        ).prefetch_related('user')

    @staticmethod
    async def list_participants(tournament: Tournament) -> List[ChallongeParticipant]:
        return await scoped(ChallongeParticipant.filter(tournament=tournament)).prefetch_related('user')

    @staticmethod
    async def participant_tournament_ids_for_user(user: User) -> Set[int]:
        rows = await scoped(ChallongeParticipant.filter(user=user)).values_list('tournament_id', flat=True)
        return set(rows)

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
            tenant_id=current_tenant_id(),
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
        return await ChallongeMatch.get_or_none(id=challonge_match_id_pk, tenant_id=current_tenant_id()).prefetch_related(
            'tournament', 'participant1__user', 'participant2__user', 'match',
        )

    @staticmethod
    async def get_challonge_match_for_match(match: Match) -> Optional[ChallongeMatch]:
        return await ChallongeMatch.get_or_none(match=match, tenant_id=current_tenant_id()).prefetch_related(
            'tournament', 'participant1__user', 'participant2__user',
        )

    @staticmethod
    async def link_match(challonge_match: ChallongeMatch, match: Match) -> None:
        challonge_match.match = match
        await challonge_match.save()

    @staticmethod
    async def count_participants(tournament: Tournament) -> int:
        return await scoped(ChallongeParticipant.filter(tournament=tournament)).count()

    @staticmethod
    async def count_matches(tournament: Tournament) -> int:
        return await scoped(ChallongeMatch.filter(tournament=tournament)).count()

    @staticmethod
    async def set_last_synced_at(tournament: Tournament, when: datetime) -> None:
        tournament.challonge_last_synced_at = when
        await tournament.save(update_fields=['challonge_last_synced_at'])

    # ------------------------------------------------------------------
    # API-usage tally (per UTC calendar month)
    # ------------------------------------------------------------------
    @staticmethod
    def _current_period() -> str:
        return datetime.now(timezone.utc).strftime('%Y-%m')

    @staticmethod
    async def increment_api_usage(count: int = 1) -> None:
        period = ChallongeRepository._current_period()
        usage, _ = await ChallongeApiUsage.get_or_create(
            tenant_id=current_tenant_id(), period=period, defaults={'request_count': 0},
        )
        usage.request_count += count
        await usage.save(update_fields=['request_count', 'updated_at'])

    @staticmethod
    async def get_monthly_usage(period: Optional[str] = None) -> int:
        period = period or ChallongeRepository._current_period()
        usage = await ChallongeApiUsage.get_or_none(period=period, tenant_id=current_tenant_id())
        return usage.request_count if usage else 0

    @staticmethod
    async def unscheduled_open_matches_for_user(user: User) -> List[ChallongeMatch]:
        """Open bracket matches the user is in that aren't yet scheduled in sglman."""
        return await scoped(ChallongeMatch.filter(
            Q(participant1__user=user) | Q(participant2__user=user),
            state=ChallongeMatchState.OPEN,
            match_id__isnull=True,
        )).prefetch_related(
            'tournament', 'participant1__user', 'participant2__user',
        )
