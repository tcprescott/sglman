"""
Match Schedule Service - Business Logic Layer

Handles match scheduling operations like seating, finishing, and seed generation.
"""

import asyncio
from datetime import datetime
from typing import Dict, Tuple, Optional

from application.repositories import MatchAcknowledgmentRepository, MatchRepository
from application.services import discord_queue
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.discord_service import DiscordService
from application.services.seedgen_service import SeedGenerationService
from models import Match, GeneratedSeeds, MatchPlayers, Commentator, Tracker, MatchWatcher, User


class MatchScheduleService:
    """Service for match scheduling operations."""
    
    # Class-level lock dictionary for seed generation
    _seed_locks: Dict[int, asyncio.Lock] = {}
    
    def __init__(self):
        self.match_repository = MatchRepository()
        self.acknowledgment_repository = MatchAcknowledgmentRepository()
        self.discord_service = DiscordService()
        self.seedgen_service = SeedGenerationService()
        self.audit_service = AuditService()

    async def seat_match(self, match: Match, actor: Optional[User] = None) -> None:
        await AuthService.ensure(
            await AuthService.can_transition_match(actor, match),
            f"User cannot seat match {match.id}",
        )
        if match.seated_at:
            raise ValueError("Match is already checked in")

        match.seated_at = datetime.now()
        await match.save()
        await self.audit_service.write_log(
            actor, AuditActions.MATCH_SEATED, {'match_id': match.id},
        )
        await match.fetch_related('tournament')
        msg = self._create_checked_in_dm_message(match.id, match.tournament.name)
        discord_queue.enqueue(self.notify_match_participants(match, msg))

    async def start_match(self, match: Match, actor: Optional[User] = None) -> None:
        await AuthService.ensure(
            await AuthService.can_transition_match(actor, match),
            f"User cannot start match {match.id}",
        )
        if not match.seated_at:
            raise ValueError("Match must be checked in before starting")
        if match.started_at:
            raise ValueError("Match is already started")

        match.started_at = datetime.now()
        await match.save()
        await self.audit_service.write_log(
            actor, AuditActions.MATCH_STARTED, {'match_id': match.id},
        )
        await match.fetch_related('tournament')
        msg = self._create_state_changed_dm_message(match.id, match.tournament.name, "Started")
        discord_queue.enqueue(self.notify_match_participants(match, msg))

    async def finish_match(self, match: Match, actor: Optional[User] = None) -> None:
        await AuthService.ensure(
            await AuthService.can_transition_match(actor, match),
            f"User cannot finish match {match.id}",
        )
        if not match.started_at:
            raise ValueError("Match must be started before finishing")
        if match.finished_at:
            raise ValueError("Match is already finished")

        match.finished_at = datetime.now()
        await match.save()
        await self.audit_service.write_log(
            actor, AuditActions.MATCH_FINISHED, {'match_id': match.id},
        )
        await match.fetch_related('tournament')
        msg = self._create_state_changed_dm_message(match.id, match.tournament.name, "Finished")
        discord_queue.enqueue(self.notify_match_participants(match, msg))

    async def confirm_match(self, match: Match, actor: Optional[User] = None) -> None:
        await AuthService.ensure(
            await AuthService.can_transition_match(actor, match),
            f"User cannot confirm match {match.id}",
        )
        if not match.finished_at:
            raise ValueError("Match must be finished before confirming")
        if match.confirmed_at:
            raise ValueError("Match is already confirmed")

        match.confirmed_at = datetime.now()
        await match.save()
        await self.audit_service.write_log(
            actor, AuditActions.MATCH_CONFIRMED, {'match_id': match.id},
        )
        await match.fetch_related('tournament')
        msg = self._create_state_changed_dm_message(match.id, match.tournament.name, "Confirmed")
        discord_queue.enqueue(self.notify_match_participants(match, msg))
    
    async def generate_seed(self, match_id: int, actor: Optional[User] = None) -> Tuple[bool, str, Optional[str]]:
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

                if not await AuthService.can_transition_match(actor, match):
                    return False, "You do not have permission to roll a seed for this match", None

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
                
                # Send DMs to players in the background (respects dm_notifications opt-out)
                async def _send_seed_dms() -> None:
                    for player in match.players:
                        if player.user.discord_id and player.user.dm_notifications:
                            dm_message = self._create_seed_dm_message(
                                player.user.display_name or player.user.username,
                                match.id,
                                match.tournament.name,
                                seed_url
                            )
                            await self.discord_service.send_dm(player.user.discord_id, dm_message)

                discord_queue.enqueue(_send_seed_dms())

                message = f"Seed generated successfully for match ID {match.id}"

                await self.audit_service.write_log(
                    actor,
                    AuditActions.MATCH_SEED_ROLLED,
                    {
                        'match_id': match.id,
                        'preset': match.tournament.seed_generator,
                        'seed_url': seed_url,
                    },
                )

                return True, message, seed_url
                
            except Exception as e:
                return False, f"Error generating seed: {str(e)}", None
    
    async def notify_match_participants(self, match: Match, message: str) -> None:
        """
        Send a DM to all opted-in players, approved crew, and watchers for a match.

        Each recipient gets exactly one DM. Anyone who is watching the match
        (whether or not they are also a player/crew) receives the DM with an
        Unwatch button so they can opt out from Discord.

        Never raises; partial DM failures are logged and swallowed so the
        calling lifecycle operation is never blocked.
        """
        try:
            recipients: dict[int, bool] = {}

            players = await MatchPlayers.filter(match=match).prefetch_related('user')
            for mp in players:
                if mp.user.dm_notifications and mp.user.discord_id:
                    recipients.setdefault(mp.user.discord_id, False)

            commentators = await Commentator.filter(match=match, approved=True).prefetch_related('user')
            for c in commentators:
                if c.user.dm_notifications and c.user.discord_id:
                    recipients.setdefault(c.user.discord_id, False)

            trackers = await Tracker.filter(match=match, approved=True).prefetch_related('user')
            for t in trackers:
                if t.user.dm_notifications and t.user.discord_id:
                    recipients.setdefault(t.user.discord_id, False)

            watchers = await MatchWatcher.filter(match=match).prefetch_related('user')
            for w in watchers:
                if w.user.dm_notifications and w.user.discord_id:
                    recipients[w.user.discord_id] = True

            for discord_id, is_watcher in recipients.items():
                if is_watcher:
                    success, err = await self.discord_service.send_dm_with_unwatch_button(
                        discord_id, message, match.id,
                    )
                else:
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

    def _create_acknowledgment_request_dm_message(
        self,
        match_id: int,
        tournament_name: str,
        scheduled_at_display: str,
        *,
        rescheduled: bool,
        stream_room_name: str = '',
        player_names: Optional[list[str]] = None,
    ) -> str:
        if rescheduled:
            details = (
                f"Your match in **{tournament_name}** has been rescheduled.\n\n"
                f"Match ID: {match_id}\n"
                f"New time: {scheduled_at_display}"
            )
        else:
            details = (
                f"A match has been scheduled for you in **{tournament_name}**.\n\n"
                f"Match ID: {match_id}\n"
                f"Scheduled for: {scheduled_at_display}"
            )
        if stream_room_name:
            details += f"\nStream Room: {stream_room_name}"
        if player_names:
            details += f"\nPlayers: {', '.join(player_names)}"
        return (
            f"{details}\n\n"
            f"Click **Acknowledge** below to confirm you've seen this."
        )

    async def notify_match_crew(self, match: Match, message: str) -> None:
        """
        Send a DM to approved commentators, trackers, and watchers for a match.

        Players are excluded — they receive a separate acknowledgment DM via
        notify_acknowledgment_request. Watchers receive the message with an
        Unwatch button so they can opt out from Discord; everyone else gets a
        plain DM. Never raises; per-DM failures are logged and swallowed.
        """
        try:
            # Player discord_ids are skipped — they get the ack DM instead.
            player_discord_ids: set[int] = set()
            players = await MatchPlayers.filter(match=match).prefetch_related('user')
            for mp in players:
                if mp.user.discord_id:
                    player_discord_ids.add(mp.user.discord_id)

            # discord_id -> is_watcher flag (watchers get the unwatch button DM)
            recipients: dict[int, bool] = {}

            commentators = await Commentator.filter(match=match, approved=True).prefetch_related('user')
            for c in commentators:
                if c.user.dm_notifications and c.user.discord_id and c.user.discord_id not in player_discord_ids:
                    recipients.setdefault(c.user.discord_id, False)

            trackers = await Tracker.filter(match=match, approved=True).prefetch_related('user')
            for t in trackers:
                if t.user.dm_notifications and t.user.discord_id and t.user.discord_id not in player_discord_ids:
                    recipients.setdefault(t.user.discord_id, False)

            watchers = await MatchWatcher.filter(match=match).prefetch_related('user')
            for w in watchers:
                if w.user.dm_notifications and w.user.discord_id and w.user.discord_id not in player_discord_ids:
                    recipients[w.user.discord_id] = True

            for discord_id, is_watcher in recipients.items():
                if is_watcher:
                    success, err = await self.discord_service.send_dm_with_unwatch_button(
                        discord_id, message, match.id,
                    )
                else:
                    success, err = await self.discord_service.send_dm(discord_id, message)
                if not success:
                    print(f"[notify_match_crew] DM failed for {discord_id}: {err}")
        except Exception as e:
            print(f"[notify_match_crew] Unexpected error for match {match.id}: {e}")

    async def notify_acknowledgment_request(
        self,
        match: Match,
        *,
        rescheduled: bool,
    ) -> None:
        """
        Send a DM with an Acknowledge button to every current match player
        whose acknowledgment is still pending and who opts in to DMs.

        Never raises; per-DM failures are logged and swallowed.
        """
        try:
            await match.fetch_related('tournament', 'stream_room')
            from application.utils.timezone import format_eastern_display
            scheduled_display = format_eastern_display(match.scheduled_at) if match.scheduled_at else ''
            players = await MatchPlayers.filter(match=match).prefetch_related('user')
            player_names = [p.user.preferred_name for p in players]
            message = self._create_acknowledgment_request_dm_message(
                match.id, match.tournament.name, scheduled_display,
                rescheduled=rescheduled,
                stream_room_name=match.stream_room.name if match.stream_room else '',
                player_names=player_names,
            )

            acks = await self.acknowledgment_repository.list_for_match(match)
            for ack in acks:
                if ack.acknowledged_at is not None:
                    continue
                if not ack.user.dm_notifications or not ack.user.discord_id:
                    continue
                success, err = await self.discord_service.send_dm_with_acknowledgment_button(
                    ack.user.discord_id, message, match.id,
                )
                if not success:
                    print(f"[notify_acknowledgment_request] DM failed for {ack.user.discord_id}: {err}")
        except Exception as e:
            print(f"[notify_acknowledgment_request] Unexpected error for match {match.id}: {e}")

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

    async def notify_tournament_subscribers_scheduled(
        self,
        match: Match,
        message: str,
        exclude_discord_ids: list,
    ) -> None:
        """
        Send match-scheduled DM with crew signup buttons to tournament subscribers.

        Never raises; per-DM failures are logged and swallowed.
        """
        try:
            from application.repositories import TournamentNotificationRepository
            has_stream_room = match.stream_room_id is not None
            subscribers = await TournamentNotificationRepository().get_match_notification_subscribers(
                match.tournament_id, has_stream_room=has_stream_room
            )
            for user in subscribers:
                if user.discord_id not in exclude_discord_ids:
                    success, err = await self.discord_service.send_dm_with_crew_buttons(
                        user.discord_id, message, match.id
                    )
                    if not success:
                        print(f"[notify_tournament_subscribers_scheduled] DM failed for {user.discord_id}: {err}")
        except Exception as e:
            print(f"[notify_tournament_subscribers_scheduled] Unexpected error for match {match.id}: {e}")

    async def notify_stream_candidate_subscribers(
        self,
        match: Match,
        exclude_discord_ids: list,
    ) -> None:
        """
        Send stream-candidate alert with crew signup buttons to opted-in subscribers.

        Skipped entirely when the match already has a stream room — those subscribers
        were already notified via notify_tournament_subscribers_scheduled.

        Never raises; per-DM failures are logged and swallowed.
        """
        if match.stream_room_id is not None:
            return

        try:
            from application.repositories import TournamentNotificationRepository
            subscribers = await TournamentNotificationRepository().get_stream_candidate_subscribers(
                match.tournament_id
            )
            await match.fetch_related('tournament')
            scheduled_display = ''
            if match.scheduled_at:
                from application.utils.timezone import format_eastern_display
                scheduled_display = format_eastern_display(match.scheduled_at)
            msg = self._create_stream_candidate_dm_message(
                match.id, match.tournament.name, scheduled_display
            )
            for user in subscribers:
                if user.discord_id not in exclude_discord_ids:
                    success, err = await self.discord_service.send_dm_with_crew_buttons(
                        user.discord_id, msg, match.id
                    )
                    if not success:
                        print(f"[notify_stream_candidate_subscribers] DM failed for {user.discord_id}: {err}")
        except Exception as e:
            print(f"[notify_stream_candidate_subscribers] Unexpected error for match {match.id}: {e}")

    def _create_stream_candidate_dm_message(
        self,
        match_id: int,
        tournament_name: str,
        scheduled_at_display: str,
    ) -> str:
        return (
            f"Match ID {match_id} in **{tournament_name}** has been flagged as a potential stream match!\n\n"
            f"Scheduled for: {scheduled_at_display}\n\n"
            f"Use the buttons below to sign up as crew."
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
