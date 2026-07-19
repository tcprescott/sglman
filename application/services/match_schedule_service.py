"""
Match Schedule Service - Business Logic Layer

Handles match scheduling operations like seating, finishing, and seed generation.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, Tuple, Optional

import discord

from application import match_events
from application.events import Event, EventType, event_bus
from application.tenant_context import require_tenant_id
from application.repositories import MatchAcknowledgmentRepository, MatchRepository
from application.services import discord_queue
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.discord_service import DiscordService
from application.services.seedgen_service import SeedGenerationService
from application.utils.discord_embeds import (
    COLOR_CHECKED_IN,
    COLOR_RESCHEDULED,
    COLOR_SCHEDULED,
    COLOR_SEED,
    COLOR_STREAM,
    match_embed,
    state_changed_embed,
)
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


def _dm_opt_ok(user: User, *, require_opt_in: bool) -> bool:
    """Whether a user can receive a DM: has a discord_id and (if required) opts in."""
    return bool(user.discord_id) and (not require_opt_in or user.dm_notifications)


async def collect_match_recipients(
    match: Match,
    *,
    include_players: bool = True,
    include_watchers: bool = True,
    exclude_players: bool = False,
    require_opt_in: bool = True,
) -> dict[int, bool]:
    """Return ``{discord_id: is_watcher}`` for a match's DM recipients.

    Players, approved commentators, and approved trackers are collected as
    non-watchers (``False``); watchers override to ``True`` (they get the
    unwatch-button DM). Insertion order is players → commentators → trackers →
    watchers, and each discord_id appears once.

    - ``include_players``: add players to the recipient set.
    - ``include_watchers``: add match watchers (with the watcher flag).
    - ``exclude_players``: drop any crew/watcher who is also a player (used by the
      crew notification, where players get a separate acknowledgment DM).
    - ``require_opt_in``: honor each user's ``dm_notifications`` opt-out. Set
      ``False`` for the subscriber-dedup pass, which only needs the ids.
    """
    tenant_id = require_tenant_id()
    recipients: dict[int, bool] = {}

    players = await MatchPlayers.filter(
        match=match, tenant_id=tenant_id
    ).prefetch_related('user')
    player_discord_ids: set[int] = {
        mp.user.discord_id for mp in players if mp.user.discord_id
    }

    def _blocked(user: User) -> bool:
        return exclude_players and user.discord_id in player_discord_ids

    if include_players:
        for mp in players:
            if _dm_opt_ok(mp.user, require_opt_in=require_opt_in):
                recipients.setdefault(mp.user.discord_id, False)

    commentators = await Commentator.filter(
        match=match, approved=True, tenant_id=tenant_id
    ).prefetch_related('user')
    for c in commentators:
        if _dm_opt_ok(c.user, require_opt_in=require_opt_in) and not _blocked(c.user):
            recipients.setdefault(c.user.discord_id, False)

    trackers = await Tracker.filter(
        match=match, approved=True, tenant_id=tenant_id
    ).prefetch_related('user')
    for t in trackers:
        if _dm_opt_ok(t.user, require_opt_in=require_opt_in) and not _blocked(t.user):
            recipients.setdefault(t.user.discord_id, False)

    if include_watchers:
        watchers = await MatchWatcher.filter(
            match=match, tenant_id=tenant_id
        ).prefetch_related('user')
        for w in watchers:
            if _dm_opt_ok(w.user, require_opt_in=require_opt_in) and not _blocked(w.user):
                recipients[w.user.discord_id] = True

    return recipients


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


async def _community_name() -> str:
    """The current tenant's community name for the embed footer, or '' if none.

    Thin alias over ``TenantService.current_community_name`` (non-raising,
    best-effort): a missing tenant or DB-less context just omits the footer
    rather than breaking a best-effort DM. The functions that need a tenant for
    their queries still enforce it with ``require_tenant_id`` as before.
    """
    from application.services.tenant_service import TenantService
    return await TenantService.current_community_name()


def _match_embed_kwargs(match: Match, community: str) -> dict:
    """Shared embed kwargs from a match with tournament/players/stream_room loaded."""
    return {
        'tournament': match.tournament.name,
        'community_name': community,
        'player_names': [p.user.preferred_name for p in match.players],
        'when': match.scheduled_at,
        'stream_room_name': match.stream_room.name if match.stream_room else None,
    }


def _checked_in_notification(match: Match, community: str) -> tuple:
    """(text, embed) for the check-in DM."""
    return (
        checked_in_dm(match.tournament.name, **_match_descriptor(match)),
        match_embed(
            title='✅ Match checked in', color=COLOR_CHECKED_IN,
            description='The match is about to begin — good luck!',
            **_match_embed_kwargs(match, community),
        ),
    )


def _state_notification(match: Match, community: str, new_state: str) -> tuple:
    """(text, embed) for a started/finished/confirmed transition DM."""
    return (
        state_changed_dm(match.tournament.name, new_state, **_match_descriptor(match)),
        state_changed_embed(
            match.tournament.name, new_state,
            community_name=community,
            player_names=[p.user.preferred_name for p in match.players],
            when=match.scheduled_at,
            stream_room_name=match.stream_room.name if match.stream_room else None,
        ),
    )


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
        build_message: Callable[[Match, str], tuple],
    ) -> None:
        """Shared match lifecycle transition: authorize, validate, stamp, audit, notify.

        ``check`` raises ValueError on a precondition failure; ``build_message``
        takes ``(match, community_name)`` and returns ``(text, embed)`` — both are
        built after the relations are fetched, in this request's tenant context.
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
        # Resolve the community name here (request context) rather than in the
        # queue worker, and pass the pre-built embed down with the text.
        community = await _community_name()
        message, embed = build_message(match, community)
        discord_queue.enqueue(self.notify_match_participants(match, message, embed))
        match_events.publish(match.id)
        event_bus.publish(Event.create(event_type, {
            'match_id': match.id,
            'tournament_id': match.tournament_id,
            'tournament': match.tournament.name,
        }, actor))

    async def seat_match(self, match: Match, actor: Optional[User] = None) -> None:
        await match.fetch_related('tournament')
        if match.tournament and match.tournament.is_racetime_enabled:
            raise ValueError(
                "Check-in is disabled for racetime.gg tournaments — the race "
                "room manages the match lifecycle."
            )

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
            build_message=lambda m, c: _checked_in_notification(m, c),
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
            build_message=lambda m, c: _state_notification(m, c, "Started"),
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
            build_message=lambda m, c: _state_notification(m, c, "Finished"),
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
            build_message=lambda m, c: _state_notification(m, c, "Confirmed"),
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

                # Roll-boundary feature-flag gate. A flag-gated randomizer reaches
                # a keyed upstream whose usage terms the community must be
                # authorized for; enforce that here (an authz-style gate at the
                # roll boundary, which already ran the permission check) rather
                # than trusting the config was created while the flag was on. This
                # fires ahead of the seedgen MOCK short-circuit, so an off flag
                # blocks the roll in dev too.
                gate_flag = self.seedgen_service.gating_flag(randomizer)
                if gate_flag is not None:
                    from application.services.feature_flag_service import FeatureFlagService
                    if not await FeatureFlagService().is_enabled(gate_flag):
                        return False, "This seed generator is not enabled for this community", None

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
                community = await _community_name()
                seed_embed = match_embed(
                    title='🎲 Seed ready', color=COLOR_SEED,
                    description=f'[Open your seed]({seed_url})',
                    tournament=match.tournament.name, community_name=community,
                    player_names=descriptor['player_names'], when=match.scheduled_at,
                    stream_room_name=match.stream_room.name if match.stream_room else None,
                    url=seed_url,
                )

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
                                player.user.discord_id, dm_message, embed=seed_embed,
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

    async def notify_match_participants(
        self, match: Match, message: str, embed: Optional[discord.Embed] = None,
    ) -> None:
        """
        Send a DM to all opted-in players, approved crew, and watchers for a match.

        Each recipient gets exactly one DM. Anyone who is watching the match
        (whether or not they are also a player/crew) receives the DM with an
        Unwatch button so they can opt out from Discord. ``embed`` is the
        colour-coded card rendered on Discord; the ``message`` text still feeds
        the web-push mirror.

        Never raises; partial DM failures are logged and swallowed so the
        calling lifecycle operation is never blocked.
        """
        try:
            recipients = await collect_match_recipients(match)
            await self._send_dms(
                match, recipients, message, embed=embed, log_label='notify_match_participants',
            )
        except Exception:
            logger.exception("notify_match_participants unexpected error for match %s", match.id)

    async def notify_match_crew(
        self, match: Match, message: str, embed: Optional[discord.Embed] = None,
    ) -> None:
        """
        Send a DM to approved commentators, trackers, and watchers for a match.

        Players are excluded — they receive a separate acknowledgment DM via
        notify_acknowledgment_request. Watchers receive the message with an
        Unwatch button so they can opt out from Discord; everyone else gets a
        plain DM. ``embed`` is the colour-coded Discord card. Never raises;
        per-DM failures are logged and swallowed.
        """
        try:
            recipients = await collect_match_recipients(
                match, include_players=False, exclude_players=True,
            )
            await self._send_dms(
                match, recipients, message, embed=embed, log_label='notify_match_crew',
            )
        except Exception:
            logger.exception("notify_match_crew unexpected error for match %s", match.id)

    async def _send_dms(
        self,
        match: Match,
        recipients: dict[int, bool],
        message: str,
        *,
        embed: Optional[discord.Embed] = None,
        log_label: str,
    ) -> None:
        """Send ``message`` to each recipient; watchers get the unwatch-button DM.

        ``recipients`` maps discord_id -> is_watcher (see collect_match_recipients).
        ``embed`` (when set) is the Discord card sent alongside; the text still
        flows to the web-push mirror. Per-DM failures are logged (prefixed with
        ``log_label``) and swallowed.
        """
        for discord_id, is_watcher in recipients.items():
            if is_watcher:
                success, err = await self.discord_service.send_dm_with_unwatch_button(
                    discord_id, message, match.id, embed=embed,
                )
            else:
                success, err = await self.discord_service.send_dm(
                    discord_id, message, embed=embed,
                )
            if not success:
                logger.warning("%s DM failed for %s: %s", log_label, discord_id, err)

    async def notify_acknowledgment_request(
        self,
        match: Match,
        *,
        rescheduled: bool,
        community: str = '',
    ) -> None:
        """
        Send a DM with an Acknowledge button to every current match player
        whose acknowledgment is still pending and who opts in to DMs.

        ``community`` is the embed-footer community name, resolved by the caller
        in request context — this coroutine is awaited later by the scope-less
        ``discord_queue`` worker, where the tenant is no longer in scope, so the
        footer must be passed in rather than looked up here.

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
            embed = match_embed(
                title='🔄 Match rescheduled' if rescheduled else '📣 Match scheduled',
                color=COLOR_RESCHEDULED if rescheduled else COLOR_SCHEDULED,
                description='Tap **Acknowledge** below to confirm you have seen this.',
                tournament=match.tournament.name, community_name=community,
                player_names=player_names, when=match.scheduled_at,
                stream_room_name=match.stream_room.name if match.stream_room else None,
            )

            acks = await self.acknowledgment_repository.list_for_match(match)
            for ack in acks:
                if ack.acknowledged_at is not None:
                    continue
                if not ack.user.dm_notifications or not ack.user.discord_id:
                    continue
                success, err = await self.discord_service.send_dm_with_acknowledgment_button(
                    ack.user.discord_id, message, match.id, embed=embed,
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
        embed: Optional[discord.Embed] = None,
    ) -> None:
        """
        Send match-scheduled DM with crew signup buttons to tournament subscribers.

        ``embed`` is the colour-coded Discord card; the ``message`` text still
        feeds the web-push mirror. Never raises; per-DM failures are logged and
        swallowed.
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
                        user.discord_id, message, match.id, embed=embed,
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
        community: str = '',
    ) -> None:
        """
        Send stream-candidate alert with crew signup buttons to opted-in subscribers.

        Skipped entirely when the match already has a stream room — those subscribers
        were already notified via notify_tournament_subscribers_scheduled.

        ``community`` is the embed-footer community name, resolved by the caller in
        request context (this runs in the scope-less ``discord_queue`` worker where
        the tenant is no longer in scope). Never raises; per-DM failures are logged
        and swallowed.
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
            player_names = [p.user.preferred_name for p in match.players]
            msg = stream_candidate_dm(
                match.tournament.name, scheduled_display,
                player_names=player_names,
            )
            embed = match_embed(
                title='🎥 Stream candidate', color=COLOR_STREAM,
                description='This match may be streamed — sign up to crew below.',
                tournament=match.tournament.name, community_name=community,
                player_names=player_names, when=match.scheduled_at,
            )
            for user in subscribers:
                if user.discord_id not in exclude_discord_ids:
                    success, err = await self.discord_service.send_dm_with_crew_buttons(
                        user.discord_id, msg, match.id, embed=embed,
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
        player_names = [p.user.preferred_name for p in match.players]
        build_message = rescheduled_dm if rescheduled else scheduled_dm
        msg = build_message(
            match.tournament.name,
            format_eastern_display(match.scheduled_at),
            player_names=player_names,
            stream_room_name=match.stream_room.name if match.stream_room else '',
        )
        community = await _community_name()
        embed = match_embed(
            title='🔄 Match rescheduled' if rescheduled else '📣 Match scheduled',
            color=COLOR_RESCHEDULED if rescheduled else COLOR_SCHEDULED,
            tournament=match.tournament.name, community_name=community,
            player_names=player_names, when=match.scheduled_at,
            stream_room_name=match.stream_room.name if match.stream_room else None,
        )
        discord_queue.enqueue(self.notify_acknowledgment_request(match, rescheduled=rescheduled, community=community))
        discord_queue.enqueue(self.notify_match_crew(match, msg, embed))

        # Collect IDs already notified to avoid duplicates in subscriber fan-out
        notified_ids = await self._collect_notified_discord_ids(match)
        discord_queue.enqueue(self.notify_tournament_subscribers_scheduled(match, msg, notified_ids, embed))
        if is_stream_candidate:
            discord_queue.enqueue(self.notify_stream_candidate_subscribers(match, notified_ids, community))

    async def notify_stream_candidate(self, match: Match) -> None:
        """Enqueue stream-candidate subscriber DMs for a match just flagged as a
        stream candidate (used when toggling the flag outside the scheduling flow)."""
        await match.fetch_related('tournament')
        notified_ids = await self._collect_notified_discord_ids(match)
        # Resolve the embed-footer community here (request context); the enqueued
        # coroutine runs later in the scope-less discord_queue worker.
        community = await _community_name()
        discord_queue.enqueue(self.notify_stream_candidate_subscribers(match, notified_ids, community))

    async def _collect_notified_discord_ids(self, match: Match) -> list:
        """
        Return the discord_ids of players and approved crew for a match.
        Used to deduplicate tournament-subscriber notifications.
        """
        recipients = await collect_match_recipients(
            match, include_watchers=False, require_opt_in=False,
        )
        return list(recipients)
