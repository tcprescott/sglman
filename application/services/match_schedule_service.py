"""
Match Schedule Service - Business Logic Layer

Handles match scheduling operations like seating, finishing, and seed generation.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, Tuple, Optional

from application import match_events
from application.events import Event, EventType, event_bus
from application.tenant_context import require_tenant_id
from application.repositories import MatchAcknowledgmentRepository, MatchRepository
from application.services import discord_queue
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.discord_service import DiscordService
from application.services.seedgen_service import SeedGenerationService
from application.utils.discord_messages import (
    acknowledgment_request_dm,
    checked_in_dm,
    rescheduled_dm,
    scheduled_dm,
    seed_dm,
    state_changed_dm,
    stream_candidate_dm,
)
from application.utils.timezone import format_eastern_display
from models import Match, GeneratedSeeds, MatchPlayers, Commentator, Tracker, MatchWatcher, User

logger = logging.getLogger(__name__)


def _match_descriptor(match: Match) -> dict:
    """Extract human-readable match fields from a match with ``players__user``,
    ``stream_room`` (and ``scheduled_at``) loaded, for passing to message builders."""
    return {
        'player_names': [p.user.preferred_name for p in match.players],
        'scheduled_at_display': (
            format_eastern_display(match.scheduled_at) if match.scheduled_at else ''
        ),
        'stream_room_name': match.stream_room.name if match.stream_room else '',
    }


class MatchScheduleService:
    """Service for match scheduling operations."""

    # Class-level lock dictionary for seed generation
    _seed_locks: Dict[int, asyncio.Lock] = {}

    def __init__(self) -> None:
        self.match_repository = MatchRepository()
        self.acknowledgment_repository = MatchAcknowledgmentRepository()
        self.discord_service = DiscordService()
        self.seedgen_service = SeedGenerationService()
        self.audit_service = AuditService()

    async def _transition(
        self,
        match: Match,
        actor: Optional[User],
        *,
        action_verb: str,
        check: Callable[[], None],
        timestamp_field: str,
        audit_action: str,
        event_type: str,
        build_message: Callable[[Match], str],
    ) -> None:
        """Shared match lifecycle transition: authorize, validate, stamp, audit, notify.

        ``check`` raises ValueError on a precondition failure; ``build_message`` is
        called after the tournament relation is fetched.
        """
        await AuthService.ensure(
            await AuthService.can_transition_match(actor, match),
            f"User cannot {action_verb} match {match.id}",
        )
        check()

        setattr(match, timestamp_field, datetime.now(timezone.utc))
        await match.save()
        await self.audit_service.write_log(
            actor, audit_action, {'match_id': match.id},
        )
        await match.fetch_related('tournament', 'players__user', 'stream_room')
        discord_queue.enqueue(self.notify_match_participants(match, build_message(match)))
        match_events.publish(match.id)
        event_bus.publish(Event.create(event_type, {
            'match_id': match.id,
            'tournament_id': match.tournament_id,
            'tournament': match.tournament.name,
        }, actor))

    async def seat_match(self, match: Match, actor: Optional[User] = None) -> None:
        def check() -> None:
            if match.seated_at:
                raise ValueError("Match is already checked in")
        await self._transition(
            match, actor,
            action_verb="seat",
            check=check,
            timestamp_field="seated_at",
            audit_action=AuditActions.MATCH_SEATED,
            event_type=EventType.MATCH_SEATED,
            build_message=lambda m: checked_in_dm(m.tournament.name, **_match_descriptor(m)),
        )

    async def start_match(self, match: Match, actor: Optional[User] = None) -> None:
        def check() -> None:
            if not match.seated_at:
                raise ValueError("Match must be checked in before starting")
            if match.started_at:
                raise ValueError("Match is already started")
        await self._transition(
            match, actor,
            action_verb="start",
            check=check,
            timestamp_field="started_at",
            audit_action=AuditActions.MATCH_STARTED,
            event_type=EventType.MATCH_STARTED,
            build_message=lambda m: state_changed_dm(m.tournament.name, "Started", **_match_descriptor(m)),
        )

    async def finish_match(self, match: Match, actor: Optional[User] = None) -> None:
        def check() -> None:
            if not match.started_at:
                raise ValueError("Match must be started before finishing")
            if match.finished_at:
                raise ValueError("Match is already finished")
        await self._transition(
            match, actor,
            action_verb="finish",
            check=check,
            timestamp_field="finished_at",
            audit_action=AuditActions.MATCH_FINISHED,
            event_type=EventType.MATCH_FINISHED,
            build_message=lambda m: state_changed_dm(m.tournament.name, "Finished", **_match_descriptor(m)),
        )

    async def confirm_match(self, match: Match, actor: Optional[User] = None) -> None:
        def check() -> None:
            if not match.finished_at:
                raise ValueError("Match must be finished before confirming")
            if match.confirmed_at:
                raise ValueError("Match is already confirmed")
        await self._transition(
            match, actor,
            action_verb="confirm",
            check=check,
            timestamp_field="confirmed_at",
            audit_action=AuditActions.MATCH_CONFIRMED,
            event_type=EventType.MATCH_CONFIRMED,
            build_message=lambda m: state_changed_dm(m.tournament.name, "Confirmed", **_match_descriptor(m)),
        )

        # Push the confirmed result to Challonge when this match mirrors a
        # bracket match. Fire-and-forget so a Challonge outage never blocks
        # confirmation; failures are visible via audit and the manual re-push.
        async def _push_challonge_result() -> None:
            from application.services.challonge_service import ChallongeService
            try:
                await ChallongeService().push_result_if_linked(match, actor)
            except Exception:  # noqa: BLE001 - logged, retried manually
                logger.exception("challonge auto-push failed for match %s", match.id)

        discord_queue.enqueue(_push_challonge_result())

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
                match = await Match.get(id=match_id, tenant_id=require_tenant_id()).prefetch_related(
                    'tournament', 'tournament__preset', 'players', 'players__user', 'stream_room'
                )

                if not await AuthService.can_transition_match(actor, match):
                    return False, "You do not have permission to roll a seed for this match", None

                # Check if seed already exists
                if match.generated_seed:
                    return False, "A seed has already been generated for this match", None

                # Resolve which randomizer + settings to roll. A Preset FK wins
                # when set (its randomizer + settings); otherwise fall back to the
                # legacy ``seed_generator`` string (hard-coded settings).
                preset = match.tournament.preset
                randomizer = preset.randomizer if preset is not None else match.tournament.seed_generator

                if not randomizer:
                    return False, "No seed generator configured for this tournament", None

                if randomizer not in self.seedgen_service.AVAILABLE_RANDOMIZERS:
                    return False, f"Seed generator '{randomizer}' not found", None

                # Generate the seed
                seed_url = await self.seedgen_service.generate_seed(randomizer, preset)

                # Create GeneratedSeeds record
                match.generated_seed = await GeneratedSeeds.create(
                    tournament=match.tournament,
                    seed_url=seed_url,
                    seed_info=f"Generated seed for match {match.id}"
                )
                await match.save()

                # Send DMs to players in the background (respects dm_notifications opt-out)
                descriptor = _match_descriptor(match)

                async def _send_seed_dms() -> None:
                    for player in match.players:
                        if player.user.discord_id and player.user.dm_notifications:
                            dm_message = seed_dm(
                                player.user.preferred_name,
                                match.tournament.name,
                                seed_url,
                                **descriptor,
                            )
                            success, err = await self.discord_service.send_dm(
                                player.user.discord_id, dm_message
                            )
                            if not success:
                                logger.warning(
                                    "seed DM failed for %s: %s", player.user.discord_id, err
                                )

                discord_queue.enqueue(_send_seed_dms())

                message = f"Seed generated successfully for match ID {match.id}"

                await self.audit_service.write_log(
                    actor,
                    AuditActions.MATCH_SEED_ROLLED,
                    {
                        'match_id': match.id,
                        'randomizer': randomizer,
                        'preset': preset.name if preset is not None else None,
                        'seed_url': seed_url,
                    },
                )

                match_events.publish(match.id)
                event_bus.publish(Event.create(EventType.MATCH_SEED_ROLLED, {
                    'match_id': match.id,
                    'tournament_id': match.tournament_id,
                    'seed_url': seed_url,
                }, actor))

                return True, message, seed_url

            except Exception:
                # Log the full traceback (reaches logs + Sentry) and return a
                # generic message rather than leaking raw randomizer/HTTP error
                # text to the user and the REST 400 detail.
                logger.exception("Seed generation failed for match %s", match_id)
                return False, "Seed generation failed. Please check the server logs.", None

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

            players = await MatchPlayers.filter(match=match, tenant_id=require_tenant_id()).prefetch_related('user')
            for mp in players:
                if mp.user.dm_notifications and mp.user.discord_id:
                    recipients.setdefault(mp.user.discord_id, False)

            commentators = await Commentator.filter(match=match, approved=True, tenant_id=require_tenant_id()).prefetch_related('user')
            for c in commentators:
                if c.user.dm_notifications and c.user.discord_id:
                    recipients.setdefault(c.user.discord_id, False)

            trackers = await Tracker.filter(match=match, approved=True, tenant_id=require_tenant_id()).prefetch_related('user')
            for t in trackers:
                if t.user.dm_notifications and t.user.discord_id:
                    recipients.setdefault(t.user.discord_id, False)

            watchers = await MatchWatcher.filter(match=match, tenant_id=require_tenant_id()).prefetch_related('user')
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
                    logger.warning("notify_match_participants DM failed for %s: %s", discord_id, err)

        except Exception:
            logger.exception("notify_match_participants unexpected error for match %s", match.id)

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
            players = await MatchPlayers.filter(match=match, tenant_id=require_tenant_id()).prefetch_related('user')
            for mp in players:
                if mp.user.discord_id:
                    player_discord_ids.add(mp.user.discord_id)

            # discord_id -> is_watcher flag (watchers get the unwatch button DM)
            recipients: dict[int, bool] = {}

            commentators = await Commentator.filter(match=match, approved=True, tenant_id=require_tenant_id()).prefetch_related('user')
            for c in commentators:
                if c.user.dm_notifications and c.user.discord_id and c.user.discord_id not in player_discord_ids:
                    recipients.setdefault(c.user.discord_id, False)

            trackers = await Tracker.filter(match=match, approved=True, tenant_id=require_tenant_id()).prefetch_related('user')
            for t in trackers:
                if t.user.dm_notifications and t.user.discord_id and t.user.discord_id not in player_discord_ids:
                    recipients.setdefault(t.user.discord_id, False)

            watchers = await MatchWatcher.filter(match=match, tenant_id=require_tenant_id()).prefetch_related('user')
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
                    logger.warning("notify_match_crew DM failed for %s: %s", discord_id, err)
        except Exception:
            logger.exception("notify_match_crew unexpected error for match %s", match.id)

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
            scheduled_display = format_eastern_display(match.scheduled_at) if match.scheduled_at else ''
            players = await MatchPlayers.filter(match=match, tenant_id=require_tenant_id()).prefetch_related('user')
            player_names = [p.user.preferred_name for p in players]
            message = acknowledgment_request_dm(
                match.tournament.name, scheduled_display,
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
                    logger.warning(
                        "notify_acknowledgment_request DM failed for %s: %s", ack.user.discord_id, err
                    )
        except Exception:
            logger.exception("notify_acknowledgment_request unexpected error for match %s", match.id)

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
                        logger.warning(
                            "notify_tournament_subscribers_scheduled DM failed for %s: %s",
                            user.discord_id, err,
                        )
        except Exception:
            logger.exception(
                "notify_tournament_subscribers_scheduled unexpected error for match %s", match.id
            )

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
            await match.fetch_related('tournament', 'players__user')
            scheduled_display = ''
            if match.scheduled_at:
                scheduled_display = format_eastern_display(match.scheduled_at)
            msg = stream_candidate_dm(
                match.tournament.name, scheduled_display,
                player_names=[p.user.preferred_name for p in match.players],
            )
            for user in subscribers:
                if user.discord_id not in exclude_discord_ids:
                    success, err = await self.discord_service.send_dm_with_crew_buttons(
                        user.discord_id, msg, match.id
                    )
                    if not success:
                        logger.warning(
                            "notify_stream_candidate_subscribers DM failed for %s: %s",
                            user.discord_id, err,
                        )
        except Exception:
            logger.exception(
                "notify_stream_candidate_subscribers unexpected error for match %s", match.id
            )

    async def notify_match_scheduled(
        self,
        match: Match,
        *,
        rescheduled: bool = False,
        is_stream_candidate: bool = False,
    ) -> None:
        """Fan out the scheduled/rescheduled notifications for a match.

        Loads the tournament/players/stream-room relations and computes the
        already-notified exclude list inline, then enqueues (in order): the
        per-player acknowledgment request, the crew DM, the tournament-subscriber
        signup DMs, and — only for a brand-new stream candidate — the
        stream-candidate subscriber DMs. Shared by create/update/request flows.
        """
        await match.fetch_related('tournament', 'players__user', 'stream_room')
        build_message = rescheduled_dm if rescheduled else scheduled_dm
        msg = build_message(
            match.tournament.name,
            format_eastern_display(match.scheduled_at),
            player_names=[p.user.preferred_name for p in match.players],
            stream_room_name=match.stream_room.name if match.stream_room else '',
        )
        discord_queue.enqueue(self.notify_acknowledgment_request(match, rescheduled=rescheduled))
        discord_queue.enqueue(self.notify_match_crew(match, msg))

        # Collect IDs already notified to avoid duplicates in subscriber fan-out
        notified_ids = await self._collect_notified_discord_ids(match)
        discord_queue.enqueue(self.notify_tournament_subscribers_scheduled(match, msg, notified_ids))
        if is_stream_candidate:
            discord_queue.enqueue(self.notify_stream_candidate_subscribers(match, notified_ids))

    async def notify_stream_candidate(self, match: Match) -> None:
        """Enqueue stream-candidate subscriber DMs for a match just flagged as a
        stream candidate (used when toggling the flag outside the scheduling flow)."""
        await match.fetch_related('tournament')
        notified_ids = await self._collect_notified_discord_ids(match)
        discord_queue.enqueue(self.notify_stream_candidate_subscribers(match, notified_ids))

    async def _collect_notified_discord_ids(self, match: Match) -> list:
        """
        Return the discord_ids of players and approved crew for a match.
        Used to deduplicate tournament-subscriber notifications.
        """
        ids: list = []
        players = await MatchPlayers.filter(match=match, tenant_id=require_tenant_id()).prefetch_related('user')
        for mp in players:
            if mp.user.discord_id:
                ids.append(mp.user.discord_id)
        commentators = await Commentator.filter(match=match, approved=True, tenant_id=require_tenant_id()).prefetch_related('user')
        for c in commentators:
            if c.user.discord_id and c.user.discord_id not in ids:
                ids.append(c.user.discord_id)
        trackers = await Tracker.filter(match=match, approved=True, tenant_id=require_tenant_id()).prefetch_related('user')
        for t in trackers:
            if t.user.discord_id and t.user.discord_id not in ids:
                ids.append(t.user.discord_id)
        return ids
