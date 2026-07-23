"""
Match Service - Business Logic Layer

Coordinates match-related operations, enforces business rules,
and orchestrates between repositories.
"""

import re
from datetime import datetime, date
from typing import List, Optional, Dict, Any, Tuple

from models import Match, MatchAcknowledgment, MatchPlayers, StationFormat, Tournament, User, StreamRoom
from application import match_events
from application.errors import require_found
from application.events import Event, EventType, event_bus
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
from application.services.match_source_guard import assert_sg_fields_unchanged
from application.services import discord_queue
from application.services.match_participants import MatchParticipants
from application.services.match_schedule_service import MatchScheduleService
from application.services.system_config_service import SystemConfigService
from application.tenant_context import require_tenant_id
from application.utils.timezone import (
    parse_eastern_datetime,
    to_eastern,
)

_STATION_REGEXES = {
    StationFormat.FREE:         re.compile(r'^.{0,50}$'),
    StationFormat.NUMERIC:      re.compile(r'^\d+$'),
    StationFormat.STRUCTURED:   re.compile(r'^[A-Za-z][0-9]{1,2}$'),
    StationFormat.ALPHANUMERIC: re.compile(r'^[A-Za-z0-9\-\s]{1,20}$'),
}


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

    @property
    def participants(self) -> MatchParticipants:
        """Roster/acknowledgment row orchestration bound to this service's repos.

        A property (rebuilt per access) rather than an ``__init__`` attribute so it
        reads the service's current repositories — this keeps it working when a
        caller assembles the service via ``object.__new__`` with hand-set repos.
        """
        return MatchParticipants(
            match_repository=self.repository,
            user_repository=self.user_repository,
            tournament_repository=self.tournament_repository,
            ack_repository=self.ack_repository,
        )

    async def _require_match(
        self, match_id: int, *, prefetch_relations: bool = True
    ) -> Match:
        """Load a match or raise :class:`NotFoundError` (API maps to 404)."""
        match = await self.repository.get_by_id(
            match_id, prefetch_relations=prefetch_relations
        )
        return require_found(match, f"Match {match_id}")

    async def get_match_by_id(self, match_id: int) -> Optional[Match]:
        return await self.repository.get_by_id(match_id)

    async def get_by_id(
        self, match_id: int, prefetch_relations: bool = True
    ) -> Optional[Match]:
        """Read-only load-or-None lookup for presentation/bot callers.

        Exposed so entry surfaces (pages/, api/, discordbot/) never reach
        through ``match_service.repository`` for a simple read.
        """
        return await self.repository.get_by_id(match_id, prefetch_relations=prefetch_relations)

    async def get_match_players(self, match: Match) -> List[MatchPlayers]:
        return await self.repository.get_players(match)

    async def get_player_names(self, match_id: int) -> str:
        """Comma-joined preferred names of a match's players (``''`` if none)."""
        players = await self.repository.get_players(match_id)
        return ', '.join(p.user.preferred_name for p in players) if players else ''

    async def list_acknowledgments(self, match: Match) -> List[MatchAcknowledgment]:
        return await self.ack_repository.list_for_match(match)

    async def get_all_matches_for_schedule(self) -> List[Match]:
        """
        Get all matches for the public schedule view.

        Returns:
            List of matches with all related data prefetched
        """
        return await self.repository.get_all_for_schedule()

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
        return await self.repository.get_for_date(
            target_date, exclude_finished, require_stream_room
        )

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
        return await self.repository.get_for_player(discord_id)

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

        await self._assert_within_tournament_hours(scheduled_at, tournament_id)

        # Resolve every referenced user up-front (one query per role list) so a
        # missing ID doesn't leave an orphan Match row behind.
        players = await self.participants.resolve_users(player_ids)
        commentators = await self.participants.resolve_users(commentator_ids or [])
        trackers = await self.participants.resolve_users(tracker_ids or [])

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

        await self.participants.ensure_enrolled(tournament_id, players)
        for user in players:
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
        await self.match_schedule_service.notify_match_scheduled(
            match, rescheduled=False, is_stream_candidate=is_stream_candidate,
        )

        match_events.publish(match.id, match_events.CREATED)
        event_bus.publish(Event.create(EventType.MATCH_CREATED, {
            'match_id': match.id,
            'tournament_id': tournament_id,
            'player_ids': player_ids,
            'is_stream_candidate': is_stream_candidate,
        }, actor))

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
        match = await self._require_match(match_id)

        await AuthService.ensure(
            await AuthService.can_crud_match(actor, match),
            f"User cannot edit match {match_id}",
        )

        # can_crud_match only authorizes the actor against the match's CURRENT
        # tournament. A reassignment must also be authorized against the TARGET
        # tournament, otherwise a Tournament Admin could move a match into (and
        # enroll its players in) a tournament they do not administer.
        if tournament_id is not None and tournament_id != match.tournament_id:
            await AuthService.ensure(
                await AuthService.is_staff(actor)
                or await AuthService.is_tournament_admin(actor, tournament_id),
                f"User cannot move match into tournament {tournament_id}",
            )

        old_scheduled_at = match.scheduled_at

        # Snapshot the existing player list so we can detect adds/removals.
        old_player_ids = {p.user_id for p in await self.repository.get_players(match)}
        if player_ids is not None:
            new_player_ids = set(player_ids)
        else:
            new_player_ids = old_player_ids
        players_changed = old_player_ids != new_player_ids

        # SpeedGaming read-only contract (PR 7): reject edits to ETL-owned fields
        # on a sourced match (schedule / players / tournament). See helper module.
        assert_sg_fields_unchanged(
            match,
            tournament_id=tournament_id,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            players_changed=players_changed,
        )

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
            # Validate against the target tournament (new one on reassignment).
            await self._assert_within_tournament_hours(
                scheduled_at, tournament_id if tournament_id is not None else match.tournament_id,
            )
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
            await self.participants.sync_players(match, player_ids, tournament_id or match.tournament_id)

        # Update commentators if provided
        if commentator_ids is not None:
            await self.participants.sync_crew(match, commentator_ids, self.commentator_repository)

        # Update trackers if provided
        if tracker_ids is not None:
            await self.participants.sync_crew(match, tracker_ids, self.tracker_repository)

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
            if scheduled_at_changed:
                # Time changed: fan out the full reschedule notification.
                await self.match_schedule_service.notify_match_scheduled(match, rescheduled=True)
            else:
                # Only the player set changed: just re-request acknowledgments.
                # Resolve the embed-footer community here (request context); the
                # enqueued coroutine runs later in the scope-less queue worker.
                from application.services.tenant_service import TenantService
                community = await TenantService.current_community_name()
                discord_queue.enqueue(self.match_schedule_service.notify_acknowledgment_request(
                    match, rescheduled=False, community=community,
                ))

        match_events.publish(match.id)
        event_bus.publish(Event.create(
            EventType.MATCH_RESCHEDULED if scheduled_at_changed else EventType.MATCH_UPDATED,
            {'match_id': match.id, 'tournament_id': match.tournament_id,
             'changed_fields': list(update_fields.keys())},
            actor,
        ))

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

        await self._assert_within_tournament_hours(scheduled_at, tournament_id)

        # Resolve every player before touching the match row so a missing user
        # doesn't leave an orphan Match behind.
        players = await self.participants.resolve_users(player_ids)

        match = await self.repository.create(
            tournament_id=tournament_id,
            scheduled_at=scheduled_at,
            comment=comment,
        )
        await self.participants.ensure_enrolled(tournament_id, players)
        for user in players:
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

        await self.match_schedule_service.notify_match_scheduled(match, rescheduled=False)

        match_events.publish(match.id, match_events.CREATED)
        event_bus.publish(Event.create(EventType.MATCH_CREATED, {
            'match_id': match.id, 'tournament_id': tournament_id, 'player_ids': player_ids,
        }, actor))

        return match

    async def set_stream_candidate(
        self,
        match_id: int,
        flag: bool,
        actor: Optional[User] = None,
    ) -> Match:
        """Toggle Match.is_stream_candidate. Stream Managers globally; TAs within their tournaments."""
        match = await self._require_match(match_id)

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
            await self.match_schedule_service.notify_stream_candidate(match)

        match_events.publish(match.id)
        event_bus.publish(Event.create(
            EventType.MATCH_STREAM_CANDIDATE_SET if flag else EventType.MATCH_STREAM_CANDIDATE_CLEARED,
            {'match_id': match.id, 'tournament_id': match.tournament_id},
            actor,
        ))

        return match

    async def assign_stage(
        self,
        match_id: int,
        stream_room_id: Optional[int],
        actor: Optional[User] = None,
    ) -> Match:
        """Assign or clear the StreamRoom for a match. Stream Managers globally; TAs within their tournaments."""
        match = await self._require_match(match_id)

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
        event_bus.publish(Event.create(
            EventType.MATCH_STAGE_ASSIGNED if stream_room_id is not None else EventType.MATCH_STAGE_CLEARED,
            {'match_id': match.id, 'tournament_id': match.tournament_id, 'stream_room_id': stream_room_id},
            actor,
        ))

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
        match = await self._require_match(match_id)

        await AuthService.ensure(
            await AuthService.can_transition_match(actor, match),
            f"User cannot assign stations for match {match_id}",
        )

        if match.tournament and match.tournament.is_racetime_enabled:
            raise ValueError(
                "Station assignment is disabled for racetime.gg tournaments — "
                "players race remotely, so there are no on-site stations to assign."
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
        event_bus.publish(Event.create(EventType.MATCH_STATIONS_ASSIGNED, {
            'match_id': match.id,
            'tournament_id': match.tournament_id,
            'assignments': {str(k): v for k, v in assignments.items()},
        }, actor))

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
        users = await self.participants.resolve_users(player_ids)
        await self.participants.ensure_enrolled(tournament_id, users)

    async def delete_match(self, match_id: int, actor: Optional[User] = None) -> None:
        match = await self._require_match(match_id)
        await AuthService.ensure(
            await AuthService.can_crud_match(actor, match),
            f"User cannot delete match {match_id}",
        )
        tournament_id = match.tournament_id
        await self.repository.delete(match)
        await self.audit_service.write_log(
            actor, AuditActions.MATCH_DELETED, {'match_id': match_id},
        )
        match_events.publish(match_id, match_events.DELETED)
        event_bus.publish(Event.create(EventType.MATCH_DELETED, {
            'match_id': match_id, 'tournament_id': tournament_id,
        }, actor))

    # Match lifecycle transitions (seat / start / finish / confirm) live solely
    # in MatchScheduleService._transition, which enforces the ordering rules and
    # emits state-change notifications. Earlier permissive seat_players /
    # finish_match duplicates were removed to keep one lifecycle path.

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
        match = await self._require_match(match_id)

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
        event_bus.publish(Event.create(EventType.MATCH_RESULT_RECORDED, {
            'match_id': match.id,
            'tournament_id': match.tournament_id,
            'winner_id': winner_id,
            'ranks': {str(k): v for k, v in ranks.items()},
        }, actor))

        return match

    async def acknowledge_match(self, match_id: int, user: User) -> MatchAcknowledgment:
        """Mark a match as acknowledged by the given player.

        Only current players of the match may acknowledge.
        """
        match = await self._require_match(match_id, prefetch_relations=False)

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
        event_bus.publish(Event.create(EventType.MATCH_ACKNOWLEDGED, {
            'match_id': match.id, 'tournament_id': match.tournament_id, 'user_id': user.id,
        }, user))
        return ack

    async def _seed_acknowledgments(
        self,
        match: Match,
        player_ids: List[int],
        actor: Optional[User],
    ) -> None:
        await self.participants.seed_acknowledgments(match, player_ids, actor)

    async def _assert_within_tournament_hours(
        self, scheduled_at: datetime, tournament_id: Optional[int],
    ) -> None:
        """Reject scheduled_at (UTC) outside the window for its date.

        Resolved for ``tournament_id``: the tournament's own per-day hours win
        when set, otherwise the tenant-wide setting applies.
        """
        tournament = await Tournament.get_or_none(id=tournament_id, tenant_id=require_tenant_id()) if tournament_id is not None else None
        eastern_dt = to_eastern(scheduled_at)
        d = eastern_dt.date()
        window = await SystemConfigService.get_tournament_window_for_date(d, tournament=tournament)
        if window is None:
            return
        open_t, close_t = window
        start_time = eastern_dt.time().replace(second=0, microsecond=0)
        if start_time < open_t or start_time >= close_t:
            raise ValueError(
                f"Matches on {d} can only start between "
                f"{open_t.strftime('%H:%M')} and {close_t.strftime('%H:%M')} (US/Eastern)."
            )
