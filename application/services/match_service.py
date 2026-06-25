"""
Match Service - Business Logic Layer

Coordinates match-related operations, enforces business rules,
and orchestrates between repositories.
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, date

import re

from models import Match, MatchAcknowledgment, MatchPlayers, StationFormat, User, StreamRoom

_STATION_REGEXES = {
    StationFormat.FREE:         re.compile(r'^.{0,50}$'),
    StationFormat.NUMERIC:      re.compile(r'^\d+$'),
    StationFormat.STRUCTURED:   re.compile(r'^[A-Za-z][0-9]{1,2}$'),
    StationFormat.ALPHANUMERIC: re.compile(r'^[A-Za-z0-9\-\s]{1,20}$'),
}
from application import match_events
from application.repositories import (
    MatchAcknowledgmentRepository,
    MatchRepository,
    StreamRoomRepository,
    TournamentRepository,
    UserRepository,
    CommentatorRepository,
    TrackerRepository,
)
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services import discord_queue
from application.services.match_schedule_service import MatchScheduleService
from application.services.system_config_service import SystemConfigService
from application.utils.discord_messages import checked_in_dm, scheduled_dm, rescheduled_dm
from application.utils.timezone import (
    parse_eastern_datetime,
    format_eastern_datetime,
    format_eastern_display,
    to_eastern,
)


class MatchService:
    """Service for match-related business operations."""
    
    def __init__(self) -> None:
        self.repository = MatchRepository()
        self.stream_room_repository = StreamRoomRepository()
        self.tournament_repository = TournamentRepository()
        self.user_repository = UserRepository()
        self.commentator_repository = CommentatorRepository()
        self.tracker_repository = TrackerRepository()
        self.ack_repository = MatchAcknowledgmentRepository()
        self.audit_service = AuditService()
        self.match_schedule_service = MatchScheduleService()
    
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

        acks = await self.ack_repository.list_for_match(match)
        return self._format_match_for_display(match, acks)

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

        ack_map = await self.ack_repository.list_for_matches([m.id for m in matches])
        return [self._format_match_for_display(m, ack_map.get(m.id, [])) for m in matches]
    
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
    
    async def get_all_matches_for_schedule(self) -> List[Match]:
        """
        Get all matches for the public schedule view.
        
        Returns:
            List of matches with all related data prefetched
        """
        return await Match.all().prefetch_related(
            'tournament', 'players', 'stream_room', 'generated_seed'
        ).order_by('scheduled_at')
    
    async def get_matches_for_date(
        self,
        target_date: date,
        exclude_finished: bool = True,
        require_stream_room: bool = True
    ) -> List[Match]:
        """
        Get all matches for a specific date with optional filters.
        
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
    
    async def group_matches_by_stream_room(
        self,
        matches: List[Match]
    ) -> Dict[int, Tuple[StreamRoom, List[Match]]]:
        """
        Group matches by their stream room.
        
        Args:
            matches: List of matches to group (must have stream_room prefetched)
            
        Returns:
            Dict mapping stream_room_id to tuple of (StreamRoom, list of matches)
        """
        matches_by_room: Dict[int, Tuple[StreamRoom, List[Match]]] = {}
        
        for match in matches:
            if match.stream_room_id not in matches_by_room:
                matches_by_room[match.stream_room_id] = (match.stream_room, [])
            matches_by_room[match.stream_room_id][1].append(match)
        
        return matches_by_room
    
    async def get_matches_for_player(self, discord_id: str) -> List[Match]:
        """
        Get all matches for a specific player by their Discord ID.
        
        Args:
            discord_id: Discord ID of the player
            
        Returns:
            List of matches where the player is participating
        """
        return await Match.filter(players__user__discord_id=discord_id)
    
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
        is_stream_candidate: bool = False,
        actor: Optional[User] = None,
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
        # Permission check: must be Staff or TA of the target tournament
        if await AuthService.is_staff(actor):
            pass
        else:
            await AuthService.ensure(
                await AuthService.is_tournament_admin(actor, tournament_id),
                f"User cannot create matches in tournament {tournament_id}",
            )

        # Business rule: Must have at least one player
        if not player_ids:
            raise ValueError("Match must have at least one player")

        # Parse datetime - input is in Eastern, convert to UTC for storage
        try:
            scheduled_at = parse_eastern_datetime(scheduled_date, scheduled_time)
        except ValueError as e:
            raise ValueError(f"Invalid date/time format: {e}") from e

        await self._assert_within_tournament_hours(scheduled_at)

        # Resolve every referenced user up-front so a missing ID doesn't leave
        # an orphan Match row behind.
        players = []
        for player_id in player_ids:
            user = await self.user_repository.get_by_id(player_id)
            if not user:
                raise ValueError(f"User {player_id} not found")
            players.append(user)

        commentators = []
        if commentator_ids:
            for comm_id in commentator_ids:
                user = await self.user_repository.get_by_id(comm_id)
                if not user:
                    raise ValueError(f"User {comm_id} not found")
                commentators.append(user)

        trackers = []
        if tracker_ids:
            for track_id in tracker_ids:
                user = await self.user_repository.get_by_id(track_id)
                if not user:
                    raise ValueError(f"User {track_id} not found")
                trackers.append(user)

        player_id_set = {u.id for u in players}
        if player_id_set & {u.id for u in commentators}:
            raise ValueError("Players cannot be assigned as commentators for the same match")
        if player_id_set & {u.id for u in trackers}:
            raise ValueError("Players cannot be assigned as trackers for the same match")

        # Create match
        match = await self.repository.create(
            tournament_id=tournament_id,
            scheduled_at=scheduled_at,
            comment=comment,
            stream_room_id=stream_room_id,
            is_stream_candidate=is_stream_candidate,
        )

        for user in players:
            await self._ensure_tournament_enrollment(user, tournament_id)
            await self.repository.add_player(match, user)

        for user in commentators:
            await self.commentator_repository.create(match=match, user=user, approved=True)

        for user in trackers:
            await self.tracker_repository.create(match=match, user=user, approved=True)
        
        await self.audit_service.write_log(
            actor,
            AuditActions.MATCH_CREATED,
            {
                'match_id': match.id,
                'tournament_id': tournament_id,
                'player_ids': player_ids,
                'commentator_ids': commentator_ids or [],
                'tracker_ids': tracker_ids or [],
                'is_stream_candidate': is_stream_candidate,
            },
        )

        # Seed per-player acknowledgments (actor auto-acks themselves)
        await self._seed_acknowledgments(match, player_ids, actor)

        # Notify participants of the newly scheduled match
        await match.fetch_related('tournament', 'players__user', 'stream_room')
        msg = scheduled_dm(
            match.tournament.name,
            format_eastern_display(match.scheduled_at),
            player_names=[p.user.preferred_name for p in match.players],
            stream_room_name=match.stream_room.name if match.stream_room else '',
        )
        discord_queue.enqueue(self.match_schedule_service.notify_acknowledgment_request(match, rescheduled=False))
        discord_queue.enqueue(self.match_schedule_service.notify_match_crew(match, msg))

        # Collect IDs already notified to avoid duplicates in subscriber fan-out
        notified_ids = await self._collect_notified_discord_ids(match)
        discord_queue.enqueue(self.match_schedule_service.notify_tournament_subscribers_scheduled(match, msg, notified_ids))
        if is_stream_candidate:
            discord_queue.enqueue(self.match_schedule_service.notify_stream_candidate_subscribers(match, notified_ids))

        match_events.publish(match.id, match_events.CREATED)

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
        clear_seated: bool = False,
        clear_started: bool = False,
        clear_finished: bool = False,
        clear_confirmed: bool = False,
        clear_seed: bool = False,
        actor: Optional[User] = None,
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
            clear_started: Clear started_at timestamp
            clear_finished: Clear finished_at timestamp
            clear_confirmed: Clear confirmed_at timestamp
            clear_seed: Clear generated seed
            clear_stream_room: Clear stream room assignment
            admin_user: User making the update
            
        Returns:
            Updated Match object
        """
        match = await self.repository.get_by_id(match_id, prefetch_relations=True)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        await AuthService.ensure(
            await AuthService.can_crud_match(actor, match),
            f"User cannot edit match {match_id}",
        )

        old_scheduled_at = match.scheduled_at

        # Snapshot the existing player list so we can detect adds/removals.
        old_player_ids = {p.user_id for p in await self.repository.get_players(match)}
        if player_ids is not None:
            new_player_ids = set(player_ids)
        else:
            new_player_ids = old_player_ids
        players_changed = old_player_ids != new_player_ids

        effective_commentator_ids = set(commentator_ids) if commentator_ids is not None else {c.user_id for c in match.commentators}
        effective_tracker_ids = set(tracker_ids) if tracker_ids is not None else {t.user_id for t in match.trackers}
        if new_player_ids & effective_commentator_ids:
            raise ValueError("Players cannot be assigned as commentators for the same match")
        if new_player_ids & effective_tracker_ids:
            raise ValueError("Players cannot be assigned as trackers for the same match")

        # Build update fields
        update_fields = {}

        if tournament_id is not None:
            update_fields['tournament_id'] = tournament_id

        if scheduled_date and scheduled_time:
            # Parse datetime - input is in Eastern, convert to UTC for storage
            scheduled_at = parse_eastern_datetime(scheduled_date, scheduled_time)
            await self._assert_within_tournament_hours(scheduled_at)
            update_fields['scheduled_at'] = scheduled_at

        if comment is not None:
            update_fields['comment'] = comment

        if clear_seated:
            update_fields['seated_at'] = None

        if clear_started:
            update_fields['started_at'] = None

        if clear_finished:
            update_fields['finished_at'] = None

        if clear_confirmed:
            update_fields['confirmed_at'] = None

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
            await self._sync_crew(match, commentator_ids, self.commentator_repository)

        # Update trackers if provided
        if tracker_ids is not None:
            await self._sync_crew(match, tracker_ids, self.tracker_repository)

        audit_details: Dict[str, Any] = {
            'match_id': match.id,
            'changed_fields': list(update_fields.keys()),
        }
        if player_ids is not None:
            audit_details['player_ids'] = player_ids
        if commentator_ids is not None:
            audit_details['commentator_ids'] = commentator_ids
        if tracker_ids is not None:
            audit_details['tracker_ids'] = tracker_ids
        await self.audit_service.write_log(
            actor, AuditActions.MATCH_UPDATED, audit_details,
        )

        # Notify participants when the match time changes on an already-scheduled match
        new_scheduled_at = update_fields.get('scheduled_at')
        scheduled_at_changed = bool(
            new_scheduled_at and old_scheduled_at and new_scheduled_at != old_scheduled_at
        )

        if scheduled_at_changed or players_changed:
            await self._seed_acknowledgments(match, list(new_player_ids), actor)
            discord_queue.enqueue(self.match_schedule_service.notify_acknowledgment_request(
                match, rescheduled=scheduled_at_changed,
            ))
            if scheduled_at_changed:
                await match.fetch_related('tournament', 'players__user', 'stream_room')
                msg = rescheduled_dm(
                    match.tournament.name,
                    format_eastern_display(new_scheduled_at),
                    player_names=[p.user.preferred_name for p in match.players],
                    stream_room_name=match.stream_room.name if match.stream_room else '',
                )
                discord_queue.enqueue(self.match_schedule_service.notify_match_crew(match, msg))
                notified_ids = await self._collect_notified_discord_ids(match)
                discord_queue.enqueue(self.match_schedule_service.notify_tournament_subscribers_scheduled(match, msg, notified_ids))

        match_events.publish(match.id)

        return match

    async def submit_match_request(
        self,
        tournament_id: int,
        scheduled_date: str,
        scheduled_time: str,
        player_ids: List[int],
        actor: User,
        comment: Optional[str] = None,
    ) -> Match:
        """Player-initiated match creation.

        Allowed when the actor is a player in the new match (typically self-vs-opponent
        in a tournament they're enrolled in). Bypasses the TA/Staff CRUD gate but
        does not grant Tournament Admin powers.
        """
        if actor is None:
            raise PermissionError("Login required to submit a match request")
        if actor.id not in player_ids:
            raise PermissionError("You may only submit match requests where you are a player")

        if not player_ids:
            raise ValueError("Match must have at least one player")

        try:
            scheduled_at = parse_eastern_datetime(scheduled_date, scheduled_time)
        except ValueError as e:
            raise ValueError(f"Invalid date/time format: {e}") from e

        await self._assert_within_tournament_hours(scheduled_at)

        # Resolve every player before touching the match row so a missing user
        # doesn't leave an orphan Match behind.
        players = []
        for player_id in player_ids:
            user = await self.user_repository.get_by_id(player_id)
            if not user:
                raise ValueError(f"User {player_id} not found")
            players.append(user)

        match = await self.repository.create(
            tournament_id=tournament_id,
            scheduled_at=scheduled_at,
            comment=comment,
        )
        for user in players:
            await self._ensure_tournament_enrollment(user, tournament_id)
            await self.repository.add_player(match, user)

        await self.audit_service.write_log(
            actor,
            AuditActions.MATCH_REQUESTED,
            {
                'match_id': match.id,
                'tournament_id': tournament_id,
                'player_ids': player_ids,
            },
        )

        await self._seed_acknowledgments(match, player_ids, actor)

        await match.fetch_related('tournament', 'players__user', 'stream_room')
        msg = scheduled_dm(
            match.tournament.name,
            format_eastern_display(match.scheduled_at),
            player_names=[p.user.preferred_name for p in match.players],
            stream_room_name=match.stream_room.name if match.stream_room else '',
        )
        discord_queue.enqueue(self.match_schedule_service.notify_acknowledgment_request(match, rescheduled=False))
        discord_queue.enqueue(self.match_schedule_service.notify_match_crew(match, msg))
        notified_ids = await self._collect_notified_discord_ids(match)
        discord_queue.enqueue(self.match_schedule_service.notify_tournament_subscribers_scheduled(match, msg, notified_ids))

        match_events.publish(match.id, match_events.CREATED)

        return match

    async def set_stream_candidate(
        self,
        match_id: int,
        flag: bool,
        actor: Optional[User] = None,
    ) -> Match:
        """Toggle Match.is_stream_candidate. Stream Managers globally; TAs within their tournaments."""
        match = await self.repository.get_by_id(match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        await AuthService.ensure(
            await AuthService.can_assign_match_stream(actor, match),
            "User cannot toggle stream candidate for this match",
        )

        was_candidate = match.is_stream_candidate
        await self.repository.update(match, is_stream_candidate=flag)

        await self.audit_service.write_log(
            actor,
            AuditActions.MATCH_STREAM_CANDIDATE_SET if flag else AuditActions.MATCH_STREAM_CANDIDATE_CLEARED,
            {'match_id': match.id},
        )

        if flag and not was_candidate:
            await match.fetch_related('tournament')
            notified_ids = await self._collect_notified_discord_ids(match)
            discord_queue.enqueue(self.match_schedule_service.notify_stream_candidate_subscribers(match, notified_ids))

        match_events.publish(match.id)

        return match

    async def assign_stage(
        self,
        match_id: int,
        stream_room_id: Optional[int],
        actor: Optional[User] = None,
    ) -> Match:
        """Assign or clear the StreamRoom for a match. Stream Managers globally; TAs within their tournaments."""
        match = await self.repository.get_by_id(match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        await AuthService.ensure(
            await AuthService.can_assign_match_stream(actor, match),
            "User cannot assign stages for this match",
        )

        await self.repository.update(match, stream_room_id=stream_room_id)

        await self.audit_service.write_log(
            actor,
            AuditActions.MATCH_STAGE_ASSIGNED if stream_room_id is not None else AuditActions.MATCH_STAGE_CLEARED,
            {'match_id': match.id, 'stream_room_id': stream_room_id},
        )

        match_events.publish(match.id)

        return match

    async def assign_stations(
        self,
        match_id: int,
        assignments: dict,
        actor: Optional[User] = None,
    ) -> Match:
        """Set MatchPlayers.assigned_station for one or more players.

        Args:
            match_id: Match to update.
            assignments: Mapping of MatchPlayers.id -> station string (or None).
            actor: User performing the assignment.
        """
        match = await self.repository.get_by_id(match_id, prefetch_relations=True)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        await AuthService.ensure(
            await AuthService.can_transition_match(actor, match),
            f"User cannot assign stations for match {match_id}",
        )

        fmt = await SystemConfigService.get_station_format()
        pattern = _STATION_REGEXES[fmt]
        for player_id, station in assignments.items():
            if station and not pattern.fullmatch(station):
                raise ValueError(
                    f"Station '{station}' does not match the required format ({fmt.value})"
                )

        for player in match.players:
            if player.id in assignments:
                player.assigned_station = assignments[player.id]
                await player.save()

        await self.audit_service.write_log(
            actor,
            AuditActions.MATCH_STATIONS_ASSIGNED,
            {
                'match_id': match.id,
                'assignments': {str(k): v for k, v in assignments.items()},
            },
        )

        match_events.publish(match.id)

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
    
    async def delete_match(self, match_id: int, actor: Optional[User] = None) -> None:
        match = await self.repository.get_by_id(match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")
        await AuthService.ensure(
            await AuthService.can_crud_match(actor, match),
            f"User cannot delete match {match_id}",
        )
        await self.repository.delete(match)
        await self.audit_service.write_log(
            actor, AuditActions.MATCH_DELETED, {'match_id': match_id},
        )
        match_events.publish(match_id, match_events.DELETED)

    async def seat_players(self, match_id: int, actor: Optional[User] = None) -> Match:
        """Mark match players as seated."""
        match = await self.repository.get_by_id(match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        await AuthService.ensure(
            await AuthService.can_transition_match(actor, match),
            f"User cannot seat match {match_id}",
        )

        await self.repository.update(match, seated_at=datetime.now())

        await self.audit_service.write_log(
            actor, AuditActions.MATCH_SEATED, {'match_id': match.id},
        )

        await match.fetch_related('tournament', 'players__user', 'stream_room')
        msg = checked_in_dm(
            match.tournament.name,
            player_names=[p.user.preferred_name for p in match.players],
            scheduled_at_display=(
                format_eastern_display(match.scheduled_at) if match.scheduled_at else ''
            ),
            stream_room_name=match.stream_room.name if match.stream_room else '',
        )
        discord_queue.enqueue(self.match_schedule_service.notify_match_participants(match, msg))

        match_events.publish(match.id)

        return match

    async def finish_match(self, match_id: int, actor: Optional[User] = None) -> Match:
        """Mark match as finished."""
        match = await self.repository.get_by_id(match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        await AuthService.ensure(
            await AuthService.can_transition_match(actor, match),
            f"User cannot finish match {match_id}",
        )

        if not match.seated_at:
            raise ValueError("Cannot finish a match that hasn't been seated")

        await self.repository.update(match, finished_at=datetime.now())

        await self.audit_service.write_log(
            actor, AuditActions.MATCH_FINISHED, {'match_id': match.id},
        )

        match_events.publish(match.id)

        return match

    async def record_match_result(
        self,
        match_id: int,
        winner_id: int,
        actor: User,
    ) -> Match:
        """Record finish ranks for a 2-player match.

        Winner gets rank 1; remaining player gets rank 2. The ``winner_id``
        is a :class:`MatchPlayers` row id, not a User id.
        """
        match = await self.repository.get_by_id(match_id, prefetch_relations=True)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        await AuthService.ensure(
            await AuthService.can_transition_match(actor, match),
            f"User cannot record results for match {match_id}",
        )

        if not match.players:
            raise ValueError("Match has no players")

        if not any(p.id == winner_id for p in match.players):
            raise ValueError("Winner is not a player in this match")

        ranks: Dict[int, int] = {}
        for player in match.players:
            player.finish_rank = 1 if player.id == winner_id else 2
            await player.save()
            ranks[player.id] = player.finish_rank

        await self.audit_service.write_log(
            actor,
            AuditActions.MATCH_RESULT_RECORDED,
            {
                'match_id': match.id,
                'winner_id': winner_id,
                'ranks': {str(k): v for k, v in ranks.items()},
            },
        )

        match_events.publish(match.id)

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

        players = await self.repository.get_players(match)
        if any(p.user_id == user.id for p in players):
            raise ValueError("Players cannot sign up as crew for their own match")

        # Create crew entry (not approved by default)
        if role == 'commentator':
            await self.commentator_repository.create(match=match, user=user, approved=False)
        else:
            await self.tracker_repository.create(match=match, user=user, approved=False)

        await self.audit_service.write_log(
            user,
            AuditActions.CREW_SIGNUP_CREATED,
            {'match_id': match_id, 'role': role},
        )

        match_events.publish(match_id)

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

        await self.audit_service.write_log(
            user,
            AuditActions.CREW_SIGNUP_REMOVED,
            {'match_id': match_id, 'role': role},
        )

        match_events.publish(match_id)

    async def acknowledge_match(self, match_id: int, user: User) -> MatchAcknowledgment:
        """Mark a match as acknowledged by the given player.

        Only current players of the match may acknowledge.
        """
        match = await self.repository.get_by_id(match_id, prefetch_relations=False)
        if not match:
            raise ValueError("Match not found")

        players = await self.repository.get_players(match)
        if not any(p.user_id == user.id for p in players):
            raise ValueError("You are not a participant of this match.")

        existing = await self.ack_repository.get(match, user)
        if existing and existing.acknowledged_at is not None:
            raise ValueError("You have already acknowledged this match.")

        ack = await self.ack_repository.upsert(match, user, acknowledged=True, auto=False)
        await self.audit_service.write_log(
            user,
            AuditActions.MATCH_ACKNOWLEDGED,
            {'match_id': match.id, 'tournament_id': match.tournament_id},
        )
        match_events.publish(match.id)
        return ack

    async def _seed_acknowledgments(
        self,
        match: Match,
        player_ids: List[int],
        actor: Optional[User],
    ) -> None:
        """Reset and re-create acknowledgment rows for all current players.

        The actor (if present among players) is auto-acknowledged.
        """
        await self.ack_repository.delete_for_match(match)
        actor_id = actor.id if actor is not None else None
        for pid in player_ids:
            user = await self.user_repository.get_by_id(pid)
            if not user:
                continue
            is_actor = actor_id is not None and pid == actor_id
            await self.ack_repository.upsert(
                match, user,
                acknowledged=is_actor,
                auto=is_actor,
            )

    async def _assert_within_tournament_hours(self, scheduled_at: datetime) -> None:
        """Raise ValueError if scheduled_at (UTC) falls outside the configured window for its date."""
        eastern_dt = to_eastern(scheduled_at)
        d = eastern_dt.date()
        window = await SystemConfigService.get_tournament_window_for_date(d)
        if window is None:
            return
        open_t, close_t = window
        start_time = eastern_dt.time().replace(second=0, microsecond=0)
        if start_time < open_t or start_time >= close_t:
            raise ValueError(
                f"Matches on {d} can only start between "
                f"{open_t.strftime('%H:%M')} and {close_t.strftime('%H:%M')} (US/Eastern)."
            )

    # Private helper methods

    def _get_match_state(self, match: Match) -> str:
        """
        Determine the current state of a match based on its timestamps.
        
        Business logic for match state progression:
        - Confirmed: match has confirmed_at timestamp
        - Finished: match has finished_at timestamp
        - Started: match has started_at timestamp
        - Checked In: match has seated_at timestamp
        - Scheduled: default state
        
        Args:
            match: Match object
            
        Returns:
            State string: 'Confirmed', 'Finished', 'Started', 'Checked In', or 'Scheduled'
        """
        if match.confirmed_at:
            return 'Confirmed'
        elif match.finished_at:
            return 'Finished'
        elif match.started_at:
            return 'Started'
        elif match.seated_at:
            return 'Checked In'
        else:
            return 'Scheduled'
    
    def _format_match_for_display(
        self,
        match: Match,
        acknowledgments: Optional[List[MatchAcknowledgment]] = None,
    ) -> Dict[str, Any]:
        """Format a match object for UI display."""
        # Get state and corresponding timestamp
        state = self._get_match_state(match)
        state_timestamp = None

        if match.confirmed_at:
            state_timestamp = format_eastern_datetime(match.confirmed_at)
        elif match.finished_at:
            state_timestamp = format_eastern_datetime(match.finished_at)
        elif match.started_at:
            state_timestamp = format_eastern_datetime(match.started_at)
        elif match.seated_at:
            state_timestamp = format_eastern_datetime(match.seated_at)
        else:
            state_timestamp = format_eastern_datetime(match.created_at)

        ack_by_user: Dict[int, MatchAcknowledgment] = {
            a.user_id: a for a in (acknowledgments or [])
        }
        acknowledgments_summary = []
        for p in match.players:
            user_id = getattr(p, 'user_id', None) or getattr(p.user, 'id', None)
            ack = ack_by_user.get(user_id) if user_id is not None else None
            acknowledged = ack is not None and ack.acknowledged_at is not None
            ts_display = (
                format_eastern_display(ack.acknowledged_at)
                if acknowledged and ack and ack.acknowledged_at else ''
            )
            discord_id = getattr(p.user, 'discord_id', None)
            acknowledgments_summary.append((
                p.user.preferred_name,
                acknowledged,
                bool(ack and ack.auto_acknowledged),
                ts_display,
                str(discord_id) if discord_id else None,
            ))

        return {
            'id': match.id,
            'tournament': match.tournament.name if match.tournament else '',
            'scheduled_at': format_eastern_datetime(match.scheduled_at) if match.scheduled_at else '',
            'state': state,
            'state_timestamp': state_timestamp,
            'players': [(p.user.preferred_name, p.finish_rank, p.assigned_station, str(p.user.discord_id) if p.user.discord_id else None) for p in match.players],
            'acknowledgments': acknowledgments_summary,
            'stream_room': match.stream_room.name if match.stream_room else '',
            'stream_room_url': (
                match.stream_room.stream_url
                if match.stream_room and match.stream_room.stream_url
                and match.stream_room.stream_url.lower().startswith(('http://', 'https://'))
                else ''
            ),
            'is_stream_candidate': match.is_stream_candidate,
            'seed': match.generated_seed.seed_url if match.generated_seed else '',
            'generated_seed': match.generated_seed.seed_url if match.generated_seed else '',
            'tournament_seed_generator': match.tournament.seed_generator if match.tournament else None,
            'commentators': [
                (
                    c.user.preferred_name,
                    c.approved,
                    c.user.discord_id,
                    c.acknowledged_at is not None,
                    format_eastern_display(c.acknowledged_at) if c.acknowledged_at else '',
                    c.id,
                )
                for c in match.commentators
            ],
            'trackers': [
                (
                    t.user.preferred_name,
                    t.approved,
                    t.user.discord_id,
                    t.acknowledged_at is not None,
                    format_eastern_display(t.acknowledged_at) if t.acknowledged_at else '',
                    t.id,
                )
                for t in match.trackers
            ],
            # Keep these for backward compatibility with existing code that may reference them
            'seated': format_eastern_datetime(match.seated_at) if match.seated_at else '',
            'finished': format_eastern_datetime(match.finished_at) if match.finished_at else '',
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
    
    async def _sync_crew(self, match: Match, new_ids: List[int], repository) -> None:
        """Sync a match's crew (commentators or trackers) to the given user-id list."""
        existing = await repository.get_by_match(match)
        existing_map = {c.user_id: c for c in existing}
        existing_ids = set(existing_map.keys())
        new_ids_set = set(new_ids)

        # Add new
        for uid in new_ids_set - existing_ids:
            user = await self.user_repository.get_by_id(uid)
            if not user:
                raise ValueError(f"User {uid} not found")
            await repository.create(match=match, user=user, approved=True)

        # Remove old
        for uid in existing_ids - new_ids_set:
            await repository.delete(existing_map[uid])

    async def _collect_notified_discord_ids(self, match: Match) -> list:
        """
        Return the discord_ids of players and approved crew for a match.
        Used to deduplicate tournament-subscriber notifications.
        """
        from models import MatchPlayers, Commentator, Tracker
        ids: list = []
        players = await MatchPlayers.filter(match=match).prefetch_related('user')
        for mp in players:
            if mp.user.discord_id:
                ids.append(mp.user.discord_id)
        commentators = await Commentator.filter(match=match, approved=True).prefetch_related('user')
        for c in commentators:
            if c.user.discord_id and c.user.discord_id not in ids:
                ids.append(c.user.discord_id)
        trackers = await Tracker.filter(match=match, approved=True).prefetch_related('user')
        for t in trackers:
            if t.user.discord_id and t.user.discord_id not in ids:
                ids.append(t.user.discord_id)
        return ids
