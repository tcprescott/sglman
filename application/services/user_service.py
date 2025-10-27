"""
User Service - Business Logic Layer

Coordinates user-related operations and enforces business rules.
"""

from typing import Dict, List, Optional, Set

from models import Tournament, TournamentPlayers, User
from application.repositories.user_repository import UserRepository


class UserService:
    """Service for user-related business operations."""
    
    def __init__(self):
        self.repository = UserRepository()
    
    async def get_user_by_discord_id(self, discord_id: str) -> Optional[User]:
        """
        Get a user by their Discord ID.
        
        Args:
            discord_id: Discord ID to look up
            
        Returns:
            User object or None if not found
        """
        return await self.repository.get_by_discord_id(discord_id)
    
    async def get_current_user_from_storage(self, storage_discord_id: Optional[str]) -> Optional[User]:
        """
        Get the current user from app.storage discord_id.
        
        Args:
            storage_discord_id: Discord ID from app.storage.user
            
        Returns:
            User object or None if not logged in or not found
        """
        if not storage_discord_id:
            return None
        
        return await self.repository.get_by_discord_id(storage_discord_id)
    
    async def get_active_tournaments_categorized(self) -> Dict[str, List[Tournament]]:
        """
        Get active tournaments categorized by staff-administered vs player tournaments.
        
        Returns:
            Dict with 'staff_tournaments' and 'player_tournaments' keys
        """
        tournaments = await Tournament.filter(is_active=True)
        
        staff_tournaments = [t for t in tournaments if t.staff_administered]
        player_tournaments = [t for t in tournaments if not t.staff_administered]
        
        return {
            'staff_tournaments': staff_tournaments,
            'player_tournaments': player_tournaments,
            'all_tournaments': tournaments
        }
    
    async def get_user_tournament_registrations(self, user: User) -> List[TournamentPlayers]:
        """
        Get all tournament registrations for a user.
        
        Args:
            user: User to get registrations for
            
        Returns:
            List of TournamentPlayers records
        """
        return await TournamentPlayers.filter(user=user)
    
    async def update_user_personal_info(
        self, 
        user: User, 
        display_name: Optional[str] = None, 
        pronouns: Optional[str] = None
    ) -> User:
        """
        Update user's personal information.
        
        Args:
            user: User to update
            display_name: New display name (optional)
            pronouns: New pronouns (optional)
            
        Returns:
            Updated user object
        """
        if display_name is not None:
            user.display_name = display_name.strip() if display_name.strip() else None
        
        if pronouns is not None:
            user.pronouns = pronouns.strip() if pronouns.strip() else None
        
        await user.save()
        return user
    
    async def update_user_tournament_registrations(
        self,
        user: User,
        selected_tournament_ids: Set[int],
        current_registrations: List[TournamentPlayers]
    ) -> None:
        """
        Update user's tournament registrations by adding/removing as needed.
        
        Args:
            user: User to update registrations for
            selected_tournament_ids: Set of tournament IDs that should be registered
            current_registrations: Current TournamentPlayers records
        """
        current_ids = set(tp.tournament_id for tp in current_registrations)
        
        # Remove deselected tournaments
        for tp in current_registrations:
            if tp.tournament_id not in selected_tournament_ids:
                await tp.delete()
        
        # Add newly selected tournaments
        for tournament_id in selected_tournament_ids:
            if tournament_id not in current_ids:
                tournament = await Tournament.get_or_none(id=tournament_id)
                if tournament:
                    await TournamentPlayers.create(user=user, tournament=tournament)
