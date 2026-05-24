"""
Match Schedule Service - Business Logic Layer

Handles match scheduling operations like seating, finishing, and seed generation.
"""

import asyncio
from datetime import datetime
from typing import Dict, Tuple, Optional

from application.repositories import MatchRepository
from application.services.discord_service import DiscordService
from application.services.seedgen_service import SeedGenerationService
from models import Match, GeneratedSeeds, MatchPlayers, Commentator, Tracker


class MatchScheduleService:
    """Service for match scheduling operations."""
    
    # Class-level lock dictionary for seed generation
    _seed_locks: Dict[int, asyncio.Lock] = {}
    
    def __init__(self):
        self.match_repository = MatchRepository()
        self.discord_service = DiscordService()
        self.seedgen_service = SeedGenerationService()
    
    async def seat_match(self, match: Match) -> None:
        """
        Mark a match as seated (checked in).

        Args:
            match: Match to seat

        Raises:
            ValueError: If match is invalid
        """
        if match.seated_at:
            raise ValueError("Match is already checked in")

        match.seated_at = datetime.now()
        await match.save()
        await match.fetch_related('tournament')
        msg = self._create_checked_in_dm_message(match.id, match.tournament.name)
        await self.notify_match_participants(match, msg)
    
    async def start_match(self, match: Match) -> None:
        """
        Mark a match as started.

        Args:
            match: Match to start

        Raises:
            ValueError: If match is invalid or not checked in
        """
        if not match.seated_at:
            raise ValueError("Match must be checked in before starting")

        if match.started_at:
            raise ValueError("Match is already started")

        match.started_at = datetime.now()
        await match.save()
        await match.fetch_related('tournament')
        msg = self._create_state_changed_dm_message(match.id, match.tournament.name, "Started")
        await self.notify_match_participants(match, msg)
    
    async def finish_match(self, match: Match) -> None:
        """
        Mark a match as finished.

        Args:
            match: Match to finish

        Raises:
            ValueError: If match is invalid or not started
        """
        if not match.started_at:
            raise ValueError("Match must be started before finishing")

        if match.finished_at:
            raise ValueError("Match is already finished")

        match.finished_at = datetime.now()
        await match.save()
        await match.fetch_related('tournament')
        msg = self._create_state_changed_dm_message(match.id, match.tournament.name, "Finished")
        await self.notify_match_participants(match, msg)
    
    async def confirm_match(self, match: Match) -> None:
        """
        Mark a match as confirmed.

        Args:
            match: Match to confirm

        Raises:
            ValueError: If match is invalid or not finished
        """
        if not match.finished_at:
            raise ValueError("Match must be finished before confirming")

        if match.confirmed_at:
            raise ValueError("Match is already confirmed")

        match.confirmed_at = datetime.now()
        await match.save()
        await match.fetch_related('tournament')
        msg = self._create_state_changed_dm_message(match.id, match.tournament.name, "Confirmed")
        await self.notify_match_participants(match, msg)
    
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
                
                # Check if seed generator is supported
                if match.tournament.seed_generator not in self.seedgen_service.AVAILABLE_RANDOMIZERS:
                    return False, f"Seed generator '{match.tournament.seed_generator}' not found", None
                
                # Generate the seed
                seed_url = await self.seedgen_service.generate_seed(match.tournament.seed_generator)
                
                # Create GeneratedSeeds record
                match.generated_seed = await GeneratedSeeds.create(
                    tournament=match.tournament,
                    seed_url=seed_url,
                    seed_info=f"Generated seed for match {match.id}"
                )
                await match.save()
                
                # Send DMs to players (respects dm_notifications opt-out)
                dm_failures = []
                for player in match.players:
                    if player.user.discord_id and player.user.dm_notifications:
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
    
    async def notify_match_participants(self, match: Match, message: str) -> None:
        """
        Send a DM to all opted-in players and approved crew for a match.

        Never raises; partial DM failures are logged and swallowed so the
        calling lifecycle operation is never blocked.
        """
        try:
            seen_ids: list[int] = []

            players = await MatchPlayers.filter(match=match).prefetch_related('user')
            for mp in players:
                if mp.user.dm_notifications and mp.user.discord_id:
                    seen_ids.append(mp.user.discord_id)

            commentators = await Commentator.filter(match=match, approved=True).prefetch_related('user')
            for c in commentators:
                if c.user.dm_notifications and c.user.discord_id and c.user.discord_id not in seen_ids:
                    seen_ids.append(c.user.discord_id)

            trackers = await Tracker.filter(match=match, approved=True).prefetch_related('user')
            for t in trackers:
                if t.user.dm_notifications and t.user.discord_id and t.user.discord_id not in seen_ids:
                    seen_ids.append(t.user.discord_id)

            for discord_id in seen_ids:
                success, err = await self.discord_service.send_dm(discord_id, message)
                if not success:
                    print(f"[notify_match_participants] DM failed for {discord_id}: {err}")

        except Exception as e:
            print(f"[notify_match_participants] Unexpected error for match {match.id}: {e}")

    def _create_scheduled_dm_message(
        self,
        match_id: int,
        tournament_name: str,
        scheduled_at_display: str,
    ) -> str:
        return (
            f"A match has been scheduled for you in **{tournament_name}**.\n\n"
            f"Match ID: {match_id}\n"
            f"Scheduled for: {scheduled_at_display}\n\n"
            f"Good luck!"
        )

    def _create_rescheduled_dm_message(
        self,
        match_id: int,
        tournament_name: str,
        new_scheduled_at_display: str,
    ) -> str:
        return (
            f"Your match in **{tournament_name}** has been rescheduled.\n\n"
            f"Match ID: {match_id}\n"
            f"New time: {new_scheduled_at_display}\n\n"
            f"Please update your calendar."
        )

    def _create_checked_in_dm_message(
        self,
        match_id: int,
        tournament_name: str,
    ) -> str:
        return (
            f"Match ID {match_id} in **{tournament_name}** has been checked in. "
            f"The match is about to begin — good luck!"
        )

    def _create_state_changed_dm_message(
        self,
        match_id: int,
        tournament_name: str,
        new_state: str,
    ) -> str:
        return (
            f"Match ID {match_id} in **{tournament_name}** is now: **{new_state}**."
        )

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
