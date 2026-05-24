"""
User Service - Business Logic Layer

Coordinates user-related operations and enforces business rules.
"""

from datetime import datetime
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
        pronouns: Optional[str] = None,
        dm_notifications: Optional[bool] = None,
    ) -> User:
        """
        Update user's personal information.

        Args:
            user: User to update
            display_name: New display name (optional)
            pronouns: New pronouns (optional)
            dm_notifications: Whether to receive Discord DM notifications (optional)

        Returns:
            Updated user object
        """
        if display_name is not None:
            user.display_name = display_name.strip() if display_name.strip() else None

        if pronouns is not None:
            user.pronouns = pronouns.strip() if pronouns.strip() else None

        if dm_notifications is not None:
            user.dm_notifications = dm_notifications

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
    
    async def create_user(
        self,
        username: str,
        display_name: Optional[str] = None,
        pronouns: Optional[str] = None,
        is_active: bool = True,
        permission: int = 0,
        discord_id: Optional[str] = None
    ) -> User:
        """
        Create a new user with validation.
        
        Args:
            username: Username (required)
            display_name: Display name
            pronouns: User pronouns
            is_active: Whether user is active
            permission: Permission level (0=User, 1=Tournament Admin, 2=Superadmin)
            discord_id: Discord ID
            
        Returns:
            The created User instance
            
        Raises:
            ValueError: If validation fails
        """
        # Validation
        if not username or not username.strip():
            raise ValueError("Username is required")
        
        return await self.repository.create(
            username=username.strip(),
            display_name=display_name.strip() if display_name else None,
            pronouns=pronouns.strip() if pronouns else None,
            is_active=is_active,
            permission=permission,
            discord_id=discord_id
        )
    
    async def update_user(
        self,
        user: User,
        display_name: Optional[str] = None,
        pronouns: Optional[str] = None,
        is_active: Optional[bool] = None,
        permission: Optional[int] = None,
        check_concurrency: bool = False,
        initial_updated_at: Optional[datetime] = None
    ) -> User:
        """
        Update an existing user with validation and optional concurrency checking.
        
        Args:
            user: User instance to update
            display_name: New display name
            pronouns: New pronouns
            is_active: New active status
            permission: New permission level
            check_concurrency: If True, check for concurrent modifications
            initial_updated_at: Expected updated_at timestamp for concurrency check
            
        Returns:
            The updated User instance
            
        Raises:
            ValueError: If validation or concurrency check fails
        """
        # Concurrency check
        if check_concurrency and initial_updated_at is not None:
            latest_user = await self.repository.get_by_id(user.id)
            if latest_user and latest_user.updated_at != initial_updated_at:
                raise ValueError("This user has been modified by another admin. Please reload and try again.")
        
        # Build update dict with only provided values
        update_data = {}
        if display_name is not None:
            update_data['display_name'] = display_name.strip() if display_name else None
        if pronouns is not None:
            update_data['pronouns'] = pronouns.strip() if pronouns else None
        if is_active is not None:
            update_data['is_active'] = is_active
        if permission is not None:
            update_data['permission'] = permission
        
        return await self.repository.update(user, **update_data)
    
    async def manage_tournament_enrollments(
        self,
        user: User,
        tournament_ids: Set[int],
        is_update: bool = True
    ) -> None:
        """
        Manage tournament enrollments for a user (add or replace).
        
        Args:
            user: User to manage enrollments for
            tournament_ids: Set of tournament IDs to enroll in
            is_update: If True, add to existing. If False, replace all enrollments
        """
        if is_update:
            # Get current registrations
            current_registrations = await self.get_user_tournament_registrations(user)
            await self.update_user_tournament_registrations(user, tournament_ids, current_registrations)
        else:
            # Add new enrollments only (for new users)
            for tournament_id in tournament_ids:
                tournament = await Tournament.get_or_none(id=tournament_id)
                if tournament:
                    await TournamentPlayers.create(user=user, tournament=tournament)
