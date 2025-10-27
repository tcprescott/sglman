"""
Match Schedule Service - Business Logic Layer

Handles match scheduling operations like seating, finishing, and seed generation.
"""

import asyncio
from datetime import datetime
from typing import Dict, Tuple, Optional

from application.repositories import MatchRepository
from application.seedgen import RANDOMIZERS
from application.services.discord_service import DiscordService
from models import Match, GeneratedSeeds


class MatchScheduleService:
    """Service for match scheduling operations."""
    
    # Class-level lock dictionary for seed generation
    _seed_locks: Dict[int, asyncio.Lock] = {}
    
    def __init__(self):
        self.match_repository = MatchRepository()
        self.discord_service = DiscordService()
    
    async def seat_match(self, match: Match) -> None:
        """
        Mark a match as seated.
        
        Args:
            match: Match to seat
            
        Raises:
            ValueError: If match is invalid
        """
        if match.seated_at:
            raise ValueError("Match is already seated")
        
        match.seated_at = datetime.now()
        await match.save()
    
    async def finish_match(self, match: Match) -> None:
        """
        Mark a match as finished.
        
        Args:
            match: Match to finish
            
        Raises:
            ValueError: If match is invalid
        """
        if match.finished_at:
            raise ValueError("Match is already finished")
        
        match.finished_at = datetime.now()
        await match.save()
    
    async def generate_seed(self, match_id: int) -> Tuple[bool, str, Optional[str]]:
        """
        Generate a seed for a match and send DMs to players.
        
        This method includes locking to prevent concurrent seed generation for the same match.
        
        Args:
            match_id: ID of the match to generate seed for
            
        Returns:
            Tuple of (success: bool, message: str, seed_url: Optional[str])
            - If successful: (True, success_message, seed_url)
            - If already in progress: (False, "Generation already in progress", None)
            - If failed: (False, error_message, None)
        """
        # Get or create lock for this match
        lock = self._seed_locks.get(match_id)
        if lock is None:
            lock = asyncio.Lock()
            self._seed_locks[match_id] = lock
        
        # Check if another generation is in progress
        if lock.locked():
            return False, "Seed generation already in progress for this match", None
        
        async with lock:
            try:
                # Fetch match with related data
                match = await Match.get(id=match_id).prefetch_related(
                    'tournament', 'players', 'players__user'
                )
                
                # Check if seed already exists
                if match.generated_seed:
                    return False, "A seed has already been generated for this match", None
                
                # Check if tournament has a seed generator
                if not match.tournament.seed_generator:
                    return False, "No seed generator configured for this tournament", None
                
                # Get the seed generator
                seed_generator = RANDOMIZERS.get(match.tournament.seed_generator)
                if not seed_generator:
                    return False, f"Seed generator '{match.tournament.seed_generator}' not found", None
                
                # Generate the seed
                seed_url = await seed_generator()
                
                # Create GeneratedSeeds record
                match.generated_seed = await GeneratedSeeds.create(
                    tournament=match.tournament,
                    seed_url=seed_url,
                    seed_info=f"Generated seed for match {match.id}"
                )
                await match.save()
                
                # Send DMs to players
                dm_failures = []
                for player in match.players:
                    if player.user.discord_id:
                        dm_message = self._create_seed_dm_message(
                            player.user.display_name or player.user.username,
                            match.id,
                            match.tournament.name,
                            seed_url
                        )
                        success, response = await self.discord_service.send_dm(
                            player.user.discord_id, dm_message
                        )
                        if not success:
                            dm_failures.append(f"{player.user.username}: {response}")
                
                # Build success message
                message = f"Seed generated successfully for match ID {match.id}"
                if dm_failures:
                    message += f"\n\nFailed to send DM to: {'; '.join(dm_failures)}"
                
                return True, message, seed_url
                
            except Exception as e:
                return False, f"Error generating seed: {str(e)}", None
    
    def _create_seed_dm_message(
        self, 
        player_name: str, 
        match_id: int, 
        tournament_name: str, 
        seed_url: str
    ) -> str:
        """
        Create a DM message for seed notification.
        
        Args:
            player_name: Player's display name
            match_id: Match ID
            tournament_name: Tournament name
            seed_url: Generated seed URL
            
        Returns:
            Formatted DM message
        """
        return (
            f"Hello {player_name},\n\n"
            f"A seed has been generated for your upcoming match (ID: {match_id}) "
            f"in the tournament '{tournament_name}'.\n\n"
            f"{seed_url}\n\n"
            f"Good luck and have fun!"
        )
