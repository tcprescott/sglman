"""
Tournament Service - Business Logic Layer

Handles tournament-related operations including creation, updates, and validation.
"""

from typing import Optional

from application.repositories import TournamentRepository
from models import Tournament


class TournamentService:
    """Service for tournament-related business operations."""
    
    def __init__(self):
        self.repository = TournamentRepository()
    
    async def create_tournament(
        self,
        name: str,
        description: Optional[str] = None,
        seed_generator: Optional[str] = None,
        bracket_url: Optional[str] = None,
        rules_url: Optional[str] = None,
        tournament_format: Optional[str] = None,
        average_match_duration: Optional[int] = None,
        max_match_duration: Optional[int] = None,
        is_active: bool = True,
        players_per_match: int = 2,
        team_size: int = 1,
        staff_administered: bool = False
    ) -> Tournament:
        """
        Create a new tournament with validation.
        
        Args:
            name: Tournament name (required)
            description: Tournament description
            seed_generator: Name of the seed generator to use
            bracket_url: URL to the tournament bracket
            rules_url: URL to the tournament rules
            tournament_format: Format description (e.g., "Swiss", "Double Elimination")
            average_match_duration: Average match duration in minutes
            max_match_duration: Maximum match duration in minutes
            is_active: Whether the tournament is active
            players_per_match: Number of players per match
            team_size: Size of each team
            staff_administered: Whether tournament is staff-administered
            
        Returns:
            The created Tournament instance
            
        Raises:
            ValueError: If validation fails
        """
        # Validation
        if not name or not name.strip():
            raise ValueError("Tournament name is required")
        
        # Handle "None" string for seed_generator
        if seed_generator == "None":
            seed_generator = None
        
        return await self.repository.create(
            name=name.strip(),
            description=description.strip() if description else None,
            seed_generator=seed_generator,
            bracket_url=bracket_url.strip() if bracket_url else None,
            rules_url=rules_url.strip() if rules_url else None,
            tournament_format=tournament_format.strip() if tournament_format else None,
            average_match_duration=average_match_duration,
            max_match_duration=max_match_duration,
            is_active=is_active,
            players_per_match=players_per_match,
            team_size=team_size,
            staff_administered=staff_administered
        )
    
    async def update_tournament(
        self,
        tournament: Tournament,
        name: Optional[str] = None,
        description: Optional[str] = None,
        seed_generator: Optional[str] = None,
        bracket_url: Optional[str] = None,
        rules_url: Optional[str] = None,
        tournament_format: Optional[str] = None,
        average_match_duration: Optional[int] = None,
        max_match_duration: Optional[int] = None,
        is_active: Optional[bool] = None,
        players_per_match: Optional[int] = None,
        team_size: Optional[int] = None,
        staff_administered: Optional[bool] = None
    ) -> Tournament:
        """
        Update an existing tournament with validation.
        
        Args:
            tournament: Tournament instance to update
            name: New tournament name
            description: New description
            seed_generator: New seed generator
            bracket_url: New bracket URL
            rules_url: New rules URL
            tournament_format: New tournament format
            average_match_duration: New average match duration
            max_match_duration: New max match duration
            is_active: New active status
            players_per_match: New players per match
            team_size: New team size
            staff_administered: New staff-administered status
            
        Returns:
            The updated Tournament instance
            
        Raises:
            ValueError: If validation fails
        """
        # Validation
        if name is not None and (not name or not name.strip()):
            raise ValueError("Tournament name cannot be empty")
        
        # Handle "None" string for seed_generator
        if seed_generator == "None":
            seed_generator = None
        
        # Build update dict with only provided values
        update_data = {}
        if name is not None:
            update_data['name'] = name.strip()
        if description is not None:
            update_data['description'] = description.strip() if description else None
        if seed_generator is not None:
            update_data['seed_generator'] = seed_generator
        if bracket_url is not None:
            update_data['bracket_url'] = bracket_url.strip() if bracket_url else None
        if rules_url is not None:
            update_data['rules_url'] = rules_url.strip() if rules_url else None
        if tournament_format is not None:
            update_data['tournament_format'] = tournament_format.strip() if tournament_format else None
        if average_match_duration is not None:
            update_data['average_match_duration'] = average_match_duration
        if max_match_duration is not None:
            update_data['max_match_duration'] = max_match_duration
        if is_active is not None:
            update_data['is_active'] = is_active
        if players_per_match is not None:
            update_data['players_per_match'] = players_per_match
        if team_size is not None:
            update_data['team_size'] = team_size
        if staff_administered is not None:
            update_data['staff_administered'] = staff_administered
        
        return await self.repository.update(tournament, **update_data)
    
    async def get_all_tournaments(self, active_only: bool = False) -> list[Tournament]:
        """
        Get all tournaments.
        
        Args:
            active_only: If True, only return active tournaments
            
        Returns:
            List of Tournament instances
        """
        return await self.repository.get_all(active_only=active_only)
    
    async def get_tournament_by_id(self, tournament_id: int) -> Optional[Tournament]:
        """
        Get a tournament by ID.
        
        Args:
            tournament_id: Tournament ID
            
        Returns:
            Tournament instance or None if not found
        """
        return await self.repository.get_by_id(tournament_id)
