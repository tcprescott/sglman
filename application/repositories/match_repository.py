"""
Match Repository - Data Access Layer

Handles all database queries related to matches.
Returns domain objects (Match, MatchPlayers, etc.) without business logic.
"""

from typing import List, Optional
from datetime import datetime, date

from models import Match, MatchPlayers, User


class MatchRepository:
    """Repository for Match-related database operations."""
    
    @staticmethod
    async def get_by_id(match_id: int, prefetch_relations: bool = True) -> Optional[Match]:
        """
        Get a match by ID.
        
        Args:
            match_id: The match ID
            prefetch_relations: Whether to prefetch related objects
            
        Returns:
            Match object or None if not found
        """
        query = Match.filter(id=match_id)
        
        if prefetch_relations:
            query = query.prefetch_related(
                'tournament',
                'players',
                'players__user',
                'stream_room',
                'generated_seed',
                'commentators',
                'commentators__user',
                'trackers',
                'trackers__user'
            )
        
        return await query.first()
    
    @staticmethod
    async def get_all(
        *,
        tournament_ids: Optional[List[int]] = None,
        stream_room_ids: Optional[List[int]] = None,
        only_upcoming: bool = False,
        user_discord_id: Optional[str] = None,
        prefetch_relations: bool = True
    ) -> List[Match]:
        """
        Get matches with optional filters.
        
        Args:
            tournament_ids: Filter by tournament IDs
            stream_room_ids: Filter by stream room IDs
            only_upcoming: Only return matches that haven't finished
            user_discord_id: Filter matches where user is a player
            prefetch_relations: Whether to prefetch related objects
            
        Returns:
            List of Match objects
        """
        query = Match.all()
        
        if only_upcoming:
            query = query.filter(finished_at__isnull=True)
        
        if tournament_ids:
            query = query.filter(tournament_id__in=tournament_ids)
        
        if stream_room_ids:
            query = query.filter(stream_room_id__in=stream_room_ids)
        
        if user_discord_id:
            query = query.filter(players__user__discord_id=user_discord_id)
        
        if prefetch_relations:
            query = query.prefetch_related(
                'tournament',
                'players',
                'players__user',
                'stream_room',
                'generated_seed',
                'commentators',
                'commentators__user',
                'trackers',
                'trackers__user'
            )
        
        return await query.order_by('scheduled_at')
    
    @staticmethod
    async def create(
        tournament_id: int,
        scheduled_at: datetime,
        comment: Optional[str] = None,
        stream_room_id: Optional[int] = None,
        is_stream_candidate: bool = False,
    ) -> Match:
        """
        Create a new match.

        Args:
            tournament_id: Tournament ID
            scheduled_at: When the match is scheduled
            comment: Optional comment
            stream_room_id: Optional stream room ID
            is_stream_candidate: Whether this match is a stream candidate

        Returns:
            Created Match object
        """
        match = await Match.create(
            tournament_id=tournament_id,
            scheduled_at=scheduled_at,
            comment=comment,
            stream_room_id=stream_room_id,
            is_stream_candidate=is_stream_candidate,
        )
        return match
    
    @staticmethod
    async def update(
        match: Match,
        **fields
    ) -> Match:
        """
        Update a match with given fields.
        
        Args:
            match: Match object to update
            **fields: Fields to update
            
        Returns:
            Updated Match object
        """
        for field, value in fields.items():
            setattr(match, field, value)
        
        await match.save()
        return match
    
    @staticmethod
    async def delete(match: Match) -> None:
        """
        Delete a match.
        
        Args:
            match: Match object to delete
        """
        await match.delete()
    
    @staticmethod
    async def add_player(match: Match, user: User) -> MatchPlayers:
        """
        Add a player to a match.
        
        Args:
            match: Match object
            user: User to add as player
            
        Returns:
            Created MatchPlayers object
        """
        return await MatchPlayers.create(match=match, user=user)
    
    @staticmethod
    async def remove_player(match: Match, user: User) -> None:
        """
        Remove a player from a match.
        
        Args:
            match: Match object
            user: User to remove
        """
        player = await MatchPlayers.filter(match=match, user=user).first()
        if player:
            await player.delete()
    
    @staticmethod
    async def get_players(match: "Match | int") -> List[MatchPlayers]:
        """
        Get all players for a match.

        Args:
            match: Match object or its id

        Returns:
            List of MatchPlayers
        """
        match_id = match.id if isinstance(match, Match) else match
        return await MatchPlayers.filter(match_id=match_id).prefetch_related('user')

    @staticmethod
    async def get_all_for_schedule() -> List[Match]:
        """
        Get all matches for the public schedule view, ordered by scheduled time.

        Returns:
            List of matches with tournament/players/stream_room/seed prefetched
        """
        return await Match.all().prefetch_related(
            'tournament', 'players', 'stream_room', 'generated_seed'
        ).order_by('scheduled_at')

    @staticmethod
    async def get_for_date(
        target_date: date,
        exclude_finished: bool = True,
        require_stream_room: bool = True,
    ) -> List[Match]:
        """
        Get matches scheduled on a given date, with optional filters.

        Args:
            target_date: The date to fetch matches for
            exclude_finished: If True, exclude matches that are finished
            require_stream_room: If True, only include matches with a stream room

        Returns:
            List of matches with all related data prefetched
        """
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())

        query = Match.filter(
            scheduled_at__gte=start_of_day,
            scheduled_at__lte=end_of_day
        )

        if exclude_finished:
            query = query.filter(finished_at=None)

        if require_stream_room:
            query = query.exclude(stream_room=None)

        return await query.prefetch_related(
            'tournament', 'stream_room', 'players', 'players__user',
            'commentators', 'commentators__user', 'trackers', 'trackers__user'
        ).order_by('scheduled_at')

    @staticmethod
    async def get_for_player(discord_id: str) -> List[Match]:
        """
        Get all matches where the given Discord user is a player.

        Args:
            discord_id: Discord ID of the player

        Returns:
            List of matches where the player is participating
        """
        return await Match.filter(players__user__discord_id=discord_id)
