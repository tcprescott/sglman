"""
Match Service - Business Logic Layer

Coordinates match-related operations, enforces business rules,
and orchestrates between repositories.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from application.errors import require_found
from application.events import Event, EventType, event_bus, match_live
from application.repositories import (
    CommentatorRepository,
    MatchAcknowledgmentRepository,
    MatchRepository,
    StageRepository,
    StationRepository,
    TournamentRepository,
    TrackerRepository,
    UserRepository,
)
from application.services._tournament_signup import record_enrolment_change
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.discord import discord_queue
from application.services.match.bracket_result_guard import (
    assert_bracket_result_editable,
)
from application.services.match.match_cancellation import CancellationMixin
from application.services.match.match_participants import MatchParticipants
from application.services.match.match_request import MatchRequestMixin
from application.services.match.match_review import MatchReviewMixin
from application.services.match.match_schedule_service import MatchScheduleService
from application.services.match.match_source_guard import assert_sg_fields_unchanged
from application.services.match.match_station_draw import StationDrawMixin
from application.services.match.match_stations import StationAssignmentMixin
from application.services.stage_service import StageService
from application.services.system_config_service import SystemConfigService
from application.services.timezone_service import TimezoneService
from application.tenant_context import require_tenant_id
from application.utils.timezone import (
    local_day_bounds,
    parse_local_datetime,
    timezone_label,
    to_local,
)
from models import (
    Match,
    MatchAcknowledgment,
    MatchPlayers,
    Stage,
    Tournament,
    User,
)


class MatchService(
    CancellationMixin, MatchRequestMixin, MatchReviewMixin, StationAssignmentMixin,
    StationDrawMixin,
):
    """Service for match-related business operations."""

    def __init__(self) -> None:
        self.repository = MatchRepository()
        self.station_repository = StationRepository()
        self.stage_repository = StageRepository()
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
        require_stage: bool = True
    ) -> List[Match]:
        """
        Get all matches for a specific date with optional filters.

        "That day" is resolved on the **display clock**, so a schedule board shows
        the day its reader means. The repository takes instants; deciding which
        instants make up a day is the rule that lives here.

        Args:
            target_date: The date to fetch matches for
            exclude_finished: If True, exclude matches that are finished
            require_stage: If True, only include matches with a stage

        Returns:
            List of matches with all related data prefetched
        """
        start, end = local_day_bounds(target_date, target_date)
        return await self.repository.scheduled_between(
            start, end, exclude_finished, require_stage
        )

    async def group_matches_by_stage(
        self,
        matches: List[Match]
    ) -> Dict[int, Tuple[Stage, List[Match]]]:
        """
        Group matches by their stage.

        Args:
            matches: List of matches to group (must have stage prefetched)

        Returns:
            Dict mapping stage_id to tuple of (Stage, list of matches)
        """
        matches_by_stage: Dict[int, Tuple[Stage, List[Match]]] = {}

        for match in matches:
            if match.stage_id not in matches_by_stage:
                matches_by_stage[match.stage_id] = (match.stage, [])
            matches_by_stage[match.stage_id][1].append(match)

        return matches_by_stage

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
        stage_id: Optional[int] = None,
        commentator_ids: Optional[List[int]] = None,
        tracker_ids: Optional[List[int]] = None,
        is_stream_candidate: bool = False,
        title: Optional[str] = None,
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
            stage_id: Optional stage ID
            commentator_ids: Optional list of commentator user IDs
            tracker_ids: Optional list of tracker user IDs
            title: Optional display label. It **replaces** the Discord scheduled
                event's whole title and names the racetime room, so a caller must
                pass something self-describing (see
                ``SchedulingMixin._game_title``); leave it None for the default
                "<tournament>: <players>" rendering.
            admin_user: User creating the match (for audit log)

        Returns:
            Created Match object

        Raises:
            ValueError: If validation fails
        """
        # Scoped read, so a foreign tournament id raises here rather than
        # producing a match that points across the tenant boundary: is_staff
        # short-circuits the check below, and assert_within_tournament_hours
        # falls through for a tournament it cannot see. submit_match_request
        # already does this.
        require_found(
            await self.tournament_repository.get_by_id(tournament_id),
            f"Tournament {tournament_id}",
        )

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
            raise ValueError("Add at least one player before creating the match.")

        await StageService().require_in_tenant(stage_id)

        # Parse datetime - input is on the caller's display clock, stored UTC
        try:
            scheduled_at = parse_local_datetime(scheduled_date, scheduled_time)
        except ValueError as e:
            raise ValueError("That date or time doesn't look right. Check the format and try again.") from e

        await self.assert_within_tournament_hours(scheduled_at, tournament_id)

        # Resolve every referenced user up-front (one query per role list) so a
        # missing ID doesn't leave an orphan Match row behind.
        players = await self.participants.resolve_users(player_ids)
        commentators = await self.participants.resolve_users(commentator_ids or [])
        trackers = await self.participants.resolve_users(tracker_ids or [])

        player_id_set = {u.id for u in players}
        if player_id_set & {u.id for u in commentators}:
            raise ValueError("A player in this match can't also crew it as a commentator.")
        if player_id_set & {u.id for u in trackers}:
            raise ValueError("A player in this match can't also crew it as a tracker.")

        # Create match
        match = await self.repository.create(
            tournament_id=tournament_id,
            scheduled_at=scheduled_at,
            comment=comment,
            stage_id=stage_id,
            is_stream_candidate=is_stream_candidate,
            title=title,
        )

        await self._record_auto_enrolments(
            await self.participants.ensure_enrolled(tournament_id, players),
            tournament_id, actor,
        )
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

        match_live.publish(match.id, match_live.CREATED)
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
        scheduled_at: Optional[datetime] = None,
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
            scheduled_at: New time as a resolved UTC instant, for a service-to-
                service caller that already holds one (an approved reschedule
                request). Takes precedence over the date/time strings, which
                exist for form input. Passing an instant avoids a
                UTC → wall-clock → UTC round trip that would resolve an
                ambiguous DST hour on whichever clock the *decider* happens to
                be reading, not the clock the request was made on.
            player_ids: New player list
            commentator_ids: New commentator list
            tracker_ids: New tracker list
            comment: New comment
            stage_id: New stage ID
            clear_seated: Clear seated_at timestamp
            clear_started: Clear started_at timestamp
            clear_finished: Clear finished_at timestamp
            clear_confirmed: Clear confirmed_at timestamp
            clear_seed: Clear generated seed
            clear_stage: Clear stage assignment
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
            scheduled_at=scheduled_at,
            players_changed=players_changed,
        )

        effective_commentator_ids = set(commentator_ids) if commentator_ids is not None else {c.user_id for c in match.commentators}
        effective_tracker_ids = set(tracker_ids) if tracker_ids is not None else {t.user_id for t in match.trackers}
        if new_player_ids & effective_commentator_ids:
            raise ValueError("A player in this match can't also crew it as a commentator.")
        if new_player_ids & effective_tracker_ids:
            raise ValueError("A player in this match can't also crew it as a tracker.")

        # Build update fields
        update_fields = {}

        if tournament_id is not None:
            # Same scoped resolve as create_match: reassignment must not be able
            # to move a match into another community's tournament.
            require_found(
                await self.tournament_repository.get_by_id(tournament_id),
                f"Tournament {tournament_id}",
            )
            update_fields['tournament_id'] = tournament_id

        if scheduled_at is None and scheduled_date and scheduled_time:
            # Parse datetime - input is on the caller's display clock, stored UTC
            scheduled_at = parse_local_datetime(scheduled_date, scheduled_time)
        if scheduled_at is not None:
            # Validate against the target tournament (new one on reassignment).
            await self.assert_within_tournament_hours(
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

        match_live.publish(match.id)
        event_bus.publish(Event.create(
            EventType.MATCH_RESCHEDULED if scheduled_at_changed else EventType.MATCH_UPDATED,
            {'match_id': match.id, 'tournament_id': match.tournament_id,
             'changed_fields': list(update_fields.keys())},
            actor,
        ))

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

        await self.audit_service.write_and_publish(
            actor,
            AuditActions.MATCH_STREAM_CANDIDATE_SET if flag else AuditActions.MATCH_STREAM_CANDIDATE_CLEARED,
            {'match_id': match.id},
            EventType.MATCH_STREAM_CANDIDATE_SET if flag else EventType.MATCH_STREAM_CANDIDATE_CLEARED,
            event_extra={'tournament_id': match.tournament_id},
        )

        if flag and not was_candidate:
            await self.match_schedule_service.notify_stream_candidate(match)

        match_live.publish(match.id)

        return match

    async def assign_stage(
        self,
        match_id: int,
        stage_id: Optional[int],
        actor: Optional[User] = None,
    ) -> Match:
        """Assign or clear the Stage for a match. Stream Managers globally; TAs within their tournaments."""
        match = await self._require_match(match_id)

        await AuthService.ensure(
            await AuthService.can_assign_match_stream(actor, match),
            "User cannot assign stages for this match",
        )
        await StageService().require_in_tenant(stage_id)

        await self.repository.update(match, stage_id=stage_id)

        await self.audit_service.write_and_publish(
            actor,
            AuditActions.MATCH_STAGE_ASSIGNED if stage_id is not None else AuditActions.MATCH_STAGE_CLEARED,
            {'match_id': match.id, 'stage_id': stage_id},
            EventType.MATCH_STAGE_ASSIGNED if stage_id is not None else EventType.MATCH_STAGE_CLEARED,
            event_extra={'tournament_id': match.tournament_id},
        )

        match_live.publish(match.id)

        return match


    async def ensure_players_enrolled(
        self,
        tournament_id: int,
        player_ids: List[int],
        actor: User,
    ) -> List[User]:
        """
        Ensure all players are enrolled in the tournament.

        Args:
            tournament_id: Tournament ID
            player_ids: List of user IDs to enroll
            actor: Who is causing the enrolment. Required, not optional: each
                row this creates is audited and announced, and an enrolment
                nobody is named for is not answerable.

        Returns:
            The users this call enrolled (empty when all were already entrants),
            so the caller can report the side effect rather than hiding it.

        Raises:
            ValueError: If any user is not found
        """
        users = await self.participants.resolve_users(player_ids)
        newly = await self.participants.ensure_enrolled(tournament_id, users)
        await self._record_auto_enrolments(newly, tournament_id, actor)
        return newly

    async def _record_auto_enrolments(
        self, newly: List[User], tournament_id: int, actor: Optional[User],
    ) -> None:
        """Audit and announce the entrants scheduling just added.

        ``MatchParticipants`` deliberately writes no audit and publishes no
        events, so the roster rows it creates as a side effect of scheduling used
        to appear from nowhere: no audit line naming who caused them, and nothing
        on the event bus, so a subscriber mirroring the roster silently drifted.
        The users it enrolled are exactly what it returns.
        """
        for user in newly:
            await record_enrolment_change(
                self.audit_service, actor, user, tournament_id, added=True,
            )

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
            await AuthService.can_run_match(actor, match),
            f"User cannot record results for match {match_id}",
        )

        if not match.players:
            raise ValueError("Match has no players")

        if not any(p.id == winner_id for p in match.players):
            raise ValueError("That player isn't part of this match.")

        # D6: one correction path. A match whose bracket game already settled is
        # corrected from the bracket, which re-advances; rewriting the ranks here
        # would leave the bracket silently disagreeing with its own game.
        from application.services.bracket_service import BracketService

        assert_bracket_result_editable(
            await BracketService().get_game_for_match(match.id)
        )

        ranks: Dict[int, int] = {}
        for player in match.players:
            player.finish_rank = 1 if player.id == winner_id else 2
            await player.save()
            ranks[player.id] = player.finish_rank

        await self.audit_service.write_and_publish(
            actor,
            AuditActions.MATCH_RESULT_RECORDED,
            {
                'match_id': match.id,
                'winner_id': winner_id,
                'ranks': {str(k): v for k, v in ranks.items()},
            },
            EventType.MATCH_RESULT_RECORDED,
            event_extra={'tournament_id': match.tournament_id},
        )

        match_live.publish(match.id)

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
        await self.audit_service.write_and_publish(
            user,
            AuditActions.MATCH_ACKNOWLEDGED,
            {'match_id': match.id, 'tournament_id': match.tournament_id},
            EventType.MATCH_ACKNOWLEDGED,
            event_extra={'user_id': user.id},
        )
        match_live.publish(match.id)
        return ack

    async def _seed_acknowledgments(
        self,
        match: Match,
        player_ids: List[int],
        actor: Optional[User],
    ) -> None:
        await self.participants.seed_acknowledgments(match, player_ids, actor)

    async def assert_within_tournament_hours(
        self, scheduled_at: datetime, tournament_id: Optional[int],
    ) -> None:
        """Reject scheduled_at (UTC) outside the window for its date.

        Resolved for ``tournament_id``: the tournament's own per-day hours win
        when set, otherwise the tenant-wide setting applies.
        """
        tournament = await Tournament.get_or_none(id=tournament_id, tenant_id=require_tenant_id()) if tournament_id is not None else None
        # Operating hours belong to the community, not the reader: "matches run
        # 09:00–22:00" means the community's clock. Resolving the day and the
        # start time in the viewer's zone instead would let two people in
        # different countries get opposite verdicts on the same instant.
        tz = await TimezoneService.tenant_timezone_name()
        local_dt = to_local(scheduled_at, tz)
        d = local_dt.date()
        window = await SystemConfigService.get_tournament_window_for_date(d, tournament=tournament)
        if window is None:
            return
        open_t, close_t = window
        start_time = local_dt.time().replace(second=0, microsecond=0)
        if start_time < open_t or start_time >= close_t:
            raise ValueError(
                f"Matches on {d} can only start between "
                f"{open_t.strftime('%H:%M')} and {close_t.strftime('%H:%M')} "
                f"({timezone_label(tz)})."
            )
