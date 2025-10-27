"""
Match Service - Business Logic Layer

Coordinates match-related operations, enforces business rules,
and orchestrates between repositories.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime

from models import Match, User
from application.repositories import (
    MatchRepository,
    StreamRoomRepository,
    TournamentRepository,
    UserRepository,
    CommentatorRepository,
    TrackerRepository,
)
from application.audit import write_audit_log


class MatchService:
    """Service for match-related business operations."""
    
    def __init__(self):
        self.repository = MatchRepository()
        self.stream_room_repository = StreamRoomRepository()
        self.tournament_repository = TournamentRepository()
        self.user_repository = UserRepository()
        self.commentator_repository = CommentatorRepository()
        self.tracker_repository = TrackerRepository()
    
    async def get_match_for_display(
        self,
        match_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get a match with all related data formatted for display.
        
        Args:
            match_id: The match ID
            
        Returns:
            Dictionary with match data or None
        """
        match = await self.repository.get_by_id(match_id, prefetch_relations=True)
        if not match:
            return None
        
        return self._format_match_for_display(match)
    
    async def get_matches_for_display(
        self,
        *,
        tournament_ids: Optional[List[int]] = None,
        stream_room_ids: Optional[List[int]] = None,
        only_upcoming: bool = False,
        user_discord_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get matches formatted for table display.
        
        Args:
            tournament_ids: Filter by tournament IDs
            stream_room_ids: Filter by stream room IDs
            only_upcoming: Only return unfinished matches
            user_discord_id: Filter by player discord ID
            
        Returns:
            List of formatted match dictionaries
        """
        matches = await self.repository.get_all(
            tournament_ids=tournament_ids,
            stream_room_ids=stream_room_ids,
            only_upcoming=only_upcoming,
            user_discord_id=user_discord_id,
            prefetch_relations=True
        )
        
        return [self._format_match_for_display(m) for m in matches]
    
    async def get_tournaments_for_filter(self) -> Dict[int, str]:
        """
        Get all tournaments formatted for filter dropdown.
        
        Returns:
            Dict mapping tournament ID to name
        """
        return await self.tournament_repository.get_all_as_dict()
    
    async def get_stream_rooms_for_filter(self) -> Dict[int, str]:
        """
        Get all stream rooms formatted for filter dropdown.
        
        Returns:
            Dict mapping stream room ID to name
        """
        return await self.stream_room_repository.get_all_as_dict()
    
    async def create_match(
        self,
        tournament_id: int,
        scheduled_date: str,
        scheduled_time: str,
        player_ids: List[int],
        comment: Optional[str] = None,
        stream_room_id: Optional[int] = None,
        commentator_ids: Optional[List[int]] = None,
        tracker_ids: Optional[List[int]] = None,
        admin_user: Optional[User] = None
    ) -> Match:
        """
        Create a new match with validation and business rules.
        
        Args:
            tournament_id: Tournament ID
            scheduled_date: Date string (YYYY-MM-DD)
            scheduled_time: Time string (HH:MM)
            player_ids: List of user IDs to add as players
            comment: Optional comment
            stream_room_id: Optional stream room ID
            commentator_ids: Optional list of commentator user IDs
            tracker_ids: Optional list of tracker user IDs
            admin_user: User creating the match (for audit log)
            
        Returns:
            Created Match object
            
        Raises:
            ValueError: If validation fails
        """
        # Business rule: Must have at least one player
        if not player_ids:
            raise ValueError("Match must have at least one player")
        
        # Parse datetime
        try:
            scheduled_at = datetime.strptime(
                f"{scheduled_date} {scheduled_time}",
                "%Y-%m-%d %H:%M"
            )
        except ValueError as e:
            raise ValueError(f"Invalid date/time format: {e}") from e
        
        # Create match
        match = await self.repository.create(
            tournament_id=tournament_id,
            scheduled_at=scheduled_at,
            comment=comment,
            stream_room_id=stream_room_id
        )
        
        # Add players and ensure they're enrolled in tournament
        for player_id in player_ids:
            user = await self.user_repository.get_by_id(player_id)
            if not user:
                raise ValueError(f"User {player_id} not found")
            await self._ensure_tournament_enrollment(user, tournament_id)
            await self.repository.add_player(match, user)
        
        # Add commentators if provided
        if commentator_ids:
            for comm_id in commentator_ids:
                user = await self.user_repository.get_by_id(comm_id)
                if not user:
                    raise ValueError(f"User {comm_id} not found")
                await self.commentator_repository.create(match=match, user=user, approved=True)
        
        # Add trackers if provided
        if tracker_ids:
            for track_id in tracker_ids:
                user = await self.user_repository.get_by_id(track_id)
                if not user:
                    raise ValueError(f"User {track_id} not found")
                await self.tracker_repository.create(match=match, user=user, approved=True)
        
        # Audit log
        if admin_user:
            await write_audit_log(
                admin_user,
                f'Created match {match.id}',
                f'Tournament: {tournament_id}, Players: {player_ids}'
            )
        
        return match
    
    async def update_match(
        self,
        match_id: int,
        *,
        tournament_id: Optional[int] = None,
        scheduled_date: Optional[str] = None,
        scheduled_time: Optional[str] = None,
        player_ids: Optional[List[int]] = None,
        commentator_ids: Optional[List[int]] = None,
        tracker_ids: Optional[List[int]] = None,
        comment: Optional[str] = None,
        stream_room_id: Optional[int] = None,
        clear_seated: bool = False,
        clear_finished: bool = False,
        clear_seed: bool = False,
        clear_stream_room: bool = False,
        admin_user: Optional[User] = None
    ) -> Match:
        """
        Update a match with validation.
        
        Args:
            match_id: Match to update
            tournament_id: New tournament ID
            scheduled_date: New date
            scheduled_time: New time
            player_ids: New player list
            commentator_ids: New commentator list
            tracker_ids: New tracker list
            comment: New comment
            stream_room_id: New stream room ID
            clear_seated: Clear seated_at timestamp
            clear_finished: Clear finished_at timestamp
            clear_seed: Clear generated seed
            clear_stream_room: Clear stream room assignment
            admin_user: User making the update
            
        Returns:
            Updated Match object
        """
        match = await self.repository.get_by_id(match_id, prefetch_relations=True)
        if not match:
            raise ValueError(f"Match {match_id} not found")
        
        # Build update fields
        update_fields = {}
        
        if tournament_id is not None:
            update_fields['tournament_id'] = tournament_id
        
        if scheduled_date and scheduled_time:
            scheduled_at = datetime.strptime(
                f"{scheduled_date} {scheduled_time}",
                "%Y-%m-%d %H:%M"
            )
            update_fields['scheduled_at'] = scheduled_at
        
        if comment is not None:
            update_fields['comment'] = comment
        
        if clear_stream_room:
            update_fields['stream_room_id'] = None
        elif stream_room_id is not None:
            update_fields['stream_room_id'] = stream_room_id
        
        if clear_seated:
            update_fields['seated_at'] = None
        
        if clear_finished:
            update_fields['finished_at'] = None
        
        if clear_seed:
            update_fields['generated_seed'] = None
        
        # Apply updates
        if update_fields:
            await self.repository.update(match, **update_fields)
        
        # Update players if provided
        if player_ids is not None:
            await self._sync_players(match, player_ids, tournament_id or match.tournament_id)
        
        # Update commentators if provided
        if commentator_ids is not None:
            await self._sync_commentators(match, commentator_ids)
        
        # Update trackers if provided
        if tracker_ids is not None:
            await self._sync_trackers(match, tracker_ids)
        
        # Audit log
        if admin_user:
            await write_audit_log(
                admin_user,
                f'Updated match {match.id}',
                f'Fields: {list(update_fields.keys())}'
            )
        
        return match
    
    async def ensure_players_enrolled(
        self,
        tournament_id: int,
        player_ids: List[int]
    ) -> None:
        """
        Ensure all players are enrolled in the tournament.
        
        Args:
            tournament_id: Tournament ID
            player_ids: List of user IDs to enroll
            
        Raises:
            ValueError: If any user is not found
        """
        for player_id in player_ids:
            user = await self.user_repository.get_by_id(player_id)
            if not user:
                raise ValueError(f"User {player_id} not found")
            await self._ensure_tournament_enrollment(user, tournament_id)
    
    async def seat_players(self, match_id: int, admin_user: Optional[User] = None) -> Match:
        """Mark match players as seated."""
        match = await self.repository.get_by_id(match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")
        
        await self.repository.update(match, seated_at=datetime.now())
        
        if admin_user:
            await write_audit_log(admin_user, f'Seated match {match.id}', '')
        
        return match
    
    async def finish_match(self, match_id: int, admin_user: Optional[User] = None) -> Match:
        """Mark match as finished."""
        match = await self.repository.get_by_id(match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")
        
        if not match.seated_at:
            raise ValueError("Cannot finish a match that hasn't been seated")
        
        await self.repository.update(match, finished_at=datetime.now())
        
        if admin_user:
            await write_audit_log(admin_user, f'Finished match {match.id}', '')
        
        return match
    
    async def signup_crew(
        self,
        match_id: int,
        user: User,
        role: str
    ) -> None:
        """
        Sign up a user as crew (commentator or tracker) for a match.
        
        Args:
            match_id: Match ID
            user: User signing up
            role: 'commentator' or 'tracker'
            
        Raises:
            ValueError: If role is invalid or user already signed up
        """
        # Validate role
        if role not in ['commentator', 'tracker']:
            raise ValueError(f"Invalid role: {role}. Must be 'commentator' or 'tracker'")
        
        # Get match with crew prefetched
        match = await self.repository.get_by_id(match_id, prefetch_relations=True)
        if not match:
            raise ValueError(f"Match {match_id} not found")
        
        # Check if user already signed up
        crew_list = match.commentators if role == 'commentator' else match.trackers
        if any(c.user_id == user.id for c in crew_list):
            raise ValueError(f"User already signed up as {role}")
        
        # Create crew entry (not approved by default)
        if role == 'commentator':
            await self.commentator_repository.create(match=match, user=user, approved=False)
        else:
            await self.tracker_repository.create(match=match, user=user, approved=False)
    
    async def undo_crew_signup(
        self,
        match_id: int,
        user: User,
        role: str
    ) -> None:
        """
        Remove a user's crew signup (commentator or tracker) from a match.
        
        Args:
            match_id: Match ID
            user: User to remove
            role: 'commentator' or 'tracker'
            
        Raises:
            ValueError: If role is invalid or user not signed up
        """
        # Validate role
        if role not in ['commentator', 'tracker']:
            raise ValueError(f"Invalid role: {role}. Must be 'commentator' or 'tracker'")
        
        # Get match with crew prefetched
        match = await self.repository.get_by_id(match_id, prefetch_relations=True)
        if not match:
            raise ValueError(f"Match {match_id} not found")
        
        # Find crew member
        crew_list = match.commentators if role == 'commentator' else match.trackers
        crew_member = next((c for c in crew_list if c.user_id == user.id), None)
        
        if not crew_member:
            raise ValueError(f"User is not signed up as {role}")
        
        # Delete crew entry
        await crew_member.delete()
    
    # Private helper methods
    
    def _format_match_for_display(self, match: Match) -> Dict[str, Any]:
        """Format a match object for UI display."""
        return {
            'id': match.id,
            'tournament': match.tournament.name if match.tournament else '',
            'scheduled_at': match.scheduled_at.strftime('%Y-%m-%d %H:%M') if match.scheduled_at else '',
            'seated': match.seated_at.strftime('%Y-%m-%d %H:%M') if match.seated_at else '',
            'finished': match.finished_at.strftime('%Y-%m-%d %H:%M') if match.finished_at else '',
            'players': [p.user.preferred_name for p in match.players],
            'stream_room': match.stream_room.name if match.stream_room else '',
            'seed': match.generated_seed.seed_url if match.generated_seed else '',
            'generated_seed': match.generated_seed.seed_url if match.generated_seed else '',
            'tournament_seed_generator': match.tournament.seed_generator if match.tournament else None,
            'commentators': [
                (c.user.preferred_name, c.approved, c.user.discord_id)
                for c in match.commentators
            ],
            'trackers': [
                (t.user.preferred_name, t.approved, t.user.discord_id)
                for t in match.trackers
            ],
        }
    
    async def _ensure_tournament_enrollment(self, user: User, tournament_id: int) -> None:
        """Ensure user is enrolled in tournament."""
        is_enrolled = await self.tournament_repository.is_player_enrolled_by_id(
            tournament_id=tournament_id,
            user=user
        )
        
        if not is_enrolled:
            await self.tournament_repository.enroll_player_by_id(
                tournament_id=tournament_id,
                user=user
            )
    
    async def _sync_players(self, match: Match, new_player_ids: List[int], tournament_id: int) -> None:
        """Sync match players to new list."""
        current_players = await self.repository.get_players(match)
        current_ids = {p.user_id for p in current_players}
        new_ids = set(new_player_ids)
        
        # Add new players
        for player_id in new_ids - current_ids:
            user = await self.user_repository.get_by_id(player_id)
            if not user:
                raise ValueError(f"User {player_id} not found")
            await self._ensure_tournament_enrollment(user, tournament_id)
            await self.repository.add_player(match, user)
        
        # Remove old players
        for player_id in current_ids - new_ids:
            user = await self.user_repository.get_by_id(player_id)
            if user:
                await self.repository.remove_player(match, user)
    
    async def _sync_commentators(self, match: Match, new_ids: List[int]) -> None:
        """Sync match commentators to new list."""
        existing = await self.commentator_repository.get_by_match(match)
        existing_map = {c.user_id: c for c in existing}
        existing_ids = set(existing_map.keys())
        new_ids_set = set(new_ids)
        
        # Add new
        for uid in new_ids_set - existing_ids:
            user = await self.user_repository.get_by_id(uid)
            if not user:
                raise ValueError(f"User {uid} not found")
            await self.commentator_repository.create(match=match, user=user, approved=True)
        
        # Remove old
        for uid in existing_ids - new_ids_set:
            await self.commentator_repository.delete(existing_map[uid])
    
    async def _sync_trackers(self, match: Match, new_ids: List[int]) -> None:
        """Sync match trackers to new list."""
        existing = await self.tracker_repository.get_by_match(match)
        existing_map = {t.user_id: t for t in existing}
        existing_ids = set(existing_map.keys())
        new_ids_set = set(new_ids)
        
        # Add new
        for uid in new_ids_set - existing_ids:
            user = await self.user_repository.get_by_id(uid)
            if not user:
                raise ValueError(f"User {uid} not found")
            await self.tracker_repository.create(match=match, user=user, approved=True)
        
        # Remove old
        for uid in existing_ids - new_ids_set:
            await self.tracker_repository.delete(existing_map[uid])
