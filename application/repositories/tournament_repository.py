"""
Tournament Repository - Data Access Layer

Handles database operations for tournaments.
"""

from typing import List, Optional

from models import Tournament, TournamentPlayers


class TournamentRepository:
    """Repository for tournament data access."""
    
    @staticmethod
    async def get_by_id(tournament_id: int, prefetch_players: bool = False) -> Optional[Tournament]:
        """
        Get a tournament by ID.
        
        Args:
            tournament_id: The tournament ID
            prefetch_players: Whether to prefetch enrolled players
            
        Returns:
            Tournament object or None
        """
        query = Tournament.filter(id=tournament_id)
        if prefetch_players:
            query = query.prefetch_related('players', 'players__user')
        return await query.first()
    
    @staticmethod
    async def get_by_ids(tournament_ids: List[int]) -> List[Tournament]:
        """
        Get tournaments by a list of IDs.
        
        Args:
            tournament_ids: List of tournament IDs
            
        Returns:
            List of Tournament objects
        """
        return await Tournament.filter(id__in=tournament_ids).order_by('name')
    
    @staticmethod
    async def get_all(
        active_only: bool = False,
        staff_only: bool = False,
        prefetch_players: bool = False
    ) -> List[Tournament]:
        """
        Get all tournaments with optional filters.
        
        Args:
            active_only: Only return active tournaments
            staff_only: Only return staff administered tournaments
            prefetch_players: Whether to prefetch enrolled players
            
        Returns:
            List of Tournament objects
        """
        query = Tournament.all().order_by('name')
        
        if active_only:
            query = query.filter(is_active=True)
        
        if staff_only:
            query = query.filter(staff_administered=True)
        
        if prefetch_players:
            query = query.prefetch_related('players', 'players__user')
        
        return await query
    
    @staticmethod
    async def get_all_as_dict(
        active_only: bool = False,
        staff_only: bool = False
    ) -> dict[int, str]:
        """
        Get all tournaments as a dict mapping ID to name.
        Useful for dropdown/select options.
        
        Args:
            active_only: Only return active tournaments
            staff_only: Only return staff tournaments
            
        Returns:
            Dict mapping tournament ID to name
        """
        tournaments = await TournamentRepository.get_all(
            active_only=active_only,
            staff_only=staff_only,
            prefetch_players=False
        )
        return {t.id: t.name for t in tournaments}
    
    @staticmethod
    async def create(
        name: str,
        description: Optional[str] = None,
        seed_generator: Optional[str] = None,
        is_active: bool = True,
        players_per_match: int = 2,
        team_size: int = 1,
        bracket_url: Optional[str] = None,
        rules_url: Optional[str] = None,
        tournament_format: Optional[str] = None,
        average_match_duration: Optional[int] = None,
        max_match_duration: Optional[int] = None,
        staff_administered: bool = False
    ) -> Tournament:
        """
        Create a new tournament.
        
        Args:
            name: Tournament name
            description: Tournament description
            seed_generator: Name of seed generator to use
            is_active: Whether tournament is active
            players_per_match: Number of players per match
            team_size: Number of players per team
            bracket_url: URL to tournament bracket
            rules_url: URL to tournament rules
            tournament_format: Format description
            average_match_duration: Average match duration in minutes
            max_match_duration: Maximum match duration in minutes
            staff_administered: Whether this is staff administered
            
        Returns:
            Created Tournament object
        """
        return await Tournament.create(
            name=name,
            description=description,
            seed_generator=seed_generator,
            is_active=is_active,
            players_per_match=players_per_match,
            team_size=team_size,
            bracket_url=bracket_url,
            rules_url=rules_url,
            tournament_format=tournament_format,
            average_match_duration=average_match_duration,
            max_match_duration=max_match_duration,
            staff_administered=staff_administered
        )
    
    @staticmethod
    async def update(tournament: Tournament, **fields) -> None:
        """
        Update tournament fields.
        
        Args:
            tournament: Tournament to update
            **fields: Fields to update
        """
        for key, value in fields.items():
            setattr(tournament, key, value)
        await tournament.save()
    
    @staticmethod
    async def delete(tournament: Tournament) -> None:
        """
        Delete a tournament.
        
        Args:
            tournament: Tournament to delete
        """
        await tournament.delete()
    
    @staticmethod
    async def enroll_player(tournament: Tournament, user) -> TournamentPlayers:
        """
        Enroll a user in a tournament.
        
        Args:
            tournament: Tournament to enroll in
            user: User to enroll
            
        Returns:
            Created TournamentPlayers object
        """
        return await TournamentPlayers.create(tournament=tournament, user=user)
    
    @staticmethod
    async def unenroll_player(tournament: Tournament, user) -> None:
        """
        Remove a user from a tournament.
        
        Args:
            tournament: Tournament to unenroll from
            user: User to unenroll
        """
        await TournamentPlayers.filter(tournament=tournament, user=user).delete()
    
    @staticmethod
    async def get_enrolled_players(tournament: Tournament) -> List:
        """
        Get all players enrolled in a tournament.
        
        Args:
            tournament: Tournament to get players for
            
        Returns:
            List of TournamentPlayers objects
        """
        return await TournamentPlayers.filter(tournament=tournament).prefetch_related('user')
    
    @staticmethod
    async def get_enrolled_players_by_user(user) -> List:
        """
        Get all tournament enrollments for a specific user.
        
        Args:
            user: User to get enrollments for
            
        Returns:
            List of TournamentPlayers objects
        """
        return await TournamentPlayers.filter(user=user).prefetch_related('tournament')
    
    @staticmethod
    async def get_enrolled_players_by_tournament_id(tournament_id: int) -> List:
        """
        Get all enrolled players for a specific tournament by ID.
        
        Args:
            tournament_id: Tournament ID
            
        Returns:
            List of TournamentPlayers objects
        """
        return await TournamentPlayers.filter(tournament_id=tournament_id).prefetch_related('user')
    
    @staticmethod
    async def is_player_enrolled(tournament: Tournament, user) -> bool:
        """
        Check if a user is enrolled in a tournament.
        
        Args:
            tournament: Tournament to check
            user: User to check
            
        Returns:
            True if enrolled, False otherwise
        """
        return await TournamentPlayers.filter(tournament=tournament, user=user).exists()
    
    @staticmethod
    async def is_player_enrolled_by_id(tournament_id: int, user) -> bool:
        """
        Check if a user is enrolled in a tournament by tournament ID.
        
        Args:
            tournament_id: Tournament ID to check
            user: User to check
            
        Returns:
            True if enrolled, False otherwise
        """
        return await TournamentPlayers.filter(tournament_id=tournament_id, user=user).exists()
    
    @staticmethod
    async def enroll_player_by_id(tournament_id: int, user) -> TournamentPlayers:
        """
        Enroll a user in a tournament by tournament ID.
        
        Args:
            tournament_id: Tournament ID to enroll in
            user: User to enroll
            
        Returns:
            Created TournamentPlayers object
        """
        return await TournamentPlayers.create(tournament_id=tournament_id, user=user)
