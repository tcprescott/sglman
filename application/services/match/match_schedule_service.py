"""
Match Schedule Service - Business Logic Layer

Handles match scheduling operations like seating, finishing, and seed generation.

The Discord DM fan-out that these operations trigger lives in
``_schedule_notifications.MatchNotificationMixin``, composed in below — split out
as pure code motion once this module outgrew the 800-line budget. Recipient
resolution shared by both halves lives in ``_match_recipients``.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, Tuple, Optional

from application.errors import MissingCredentialError
from application.events import match_live
from application.events import Event, EventType, event_bus
from application.tenant_context import require_tenant_id
from application.repositories import MatchAcknowledgmentRepository, MatchRepository
from application.services.discord import discord_queue
from application.services.audit_service import AuditActions, AuditService
from application.services.auth_service import AuthService
from application.services.discord.discord_service import DiscordService
from application.services.match._dm_context import (  # noqa: F401  (re-exported)
    _community_name,
    bracket_dm_context,
    bracket_line_for,
)
from application.services.match._match_recipients import (  # noqa: F401  (re-exported)
    _dm_opt_ok,
    collect_match_recipients,
)
from application.services.match._schedule_notifications import MatchNotificationMixin
from application.services.seedgen_service import SeedGenerationService
from application.utils.discord_embeds import (
    COLOR_CHECKED_IN,
    COLOR_SEED,
    match_embed,
    state_changed_embed,
)
from application.utils.discord_messages import (
    checked_in_dm,
    seed_dm,
    state_changed_dm,
)
from application.utils.timezone import format_eastern_display
from models import Match, GeneratedSeeds, User

logger = logging.getLogger(__name__)



def _match_descriptor(match: Match, bracket_line: str = '') -> dict:
    """Extract human-readable match fields from a match with ``players__user``,
    ``stream_room`` (and ``scheduled_at``) loaded, for passing to message builders.

    ``bracket_line`` is the caller-resolved series context ("Semifinals · Game 2
    of 3 · Series 1-0"); it is passed in rather than looked up here because this
    is a sync projection and the lookup is a query. '' for a match no bracket
    scheduled, which is almost all of them.
    """
    return {
        'player_names': [p.user.preferred_name for p in match.players],
        'scheduled_at_display': (
            format_eastern_display(match.scheduled_at) if match.scheduled_at else ''
        ),
        'stream_room_name': match.stream_room.name if match.stream_room else '',
        'bracket_line': bracket_line,
    }


def _match_embed_kwargs(match: Match, community: str) -> dict:
    """Shared embed kwargs from a match with tournament/players/stream_room loaded."""
    return {
        'tournament': match.tournament.name,
        'community_name': community,
        'player_names': [p.user.preferred_name for p in match.players],
        'when': match.scheduled_at,
        'stream_room_name': match.stream_room.name if match.stream_room else None,
    }


def _checked_in_notification(
    match: Match, community: str, bracket_line: str = '',
) -> tuple:
    """(text, embed) for the check-in DM."""
    return (
        checked_in_dm(match.tournament.name, **_match_descriptor(match, bracket_line)),
        match_embed(
            title='✅ Match checked in', color=COLOR_CHECKED_IN,
            description='The match is about to begin — good luck!',
            **_match_embed_kwargs(match, community),
        ),
    )


def _state_notification(
    match: Match, community: str, new_state: str, bracket_line: str = '',
) -> tuple:
    """(text, embed) for a started/finished/confirmed transition DM."""
    return (
        state_changed_dm(
            match.tournament.name, new_state, **_match_descriptor(match, bracket_line),
        ),
        state_changed_embed(
            match.tournament.name, new_state,
            community_name=community,
            player_names=[p.user.preferred_name for p in match.players],
            when=match.scheduled_at,
            stream_room_name=match.stream_room.name if match.stream_room else None,
        ),
    )


class MatchScheduleService(MatchNotificationMixin):
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
        build_message: Callable[[Match, str, str], tuple],
        authorize: Optional[Callable] = None,
    ) -> None:
        """Shared match lifecycle transition: authorize, validate, stamp, audit, notify.

        ``check`` raises ValueError on a precondition failure; ``build_message``
        takes ``(match, community_name, bracket_line)`` and returns
        ``(text, embed)`` — all three are resolved after the relations are
        fetched, in this request's tenant context, because the queue worker that
        sends the DM has neither the relations nor the tenant.

        ``authorize`` defaults to ``AuthService.can_run_match`` — the gate for
        the floor transitions a proctor owns. ``confirm_match`` overrides it with
        ``AuthService.can_confirm_match``, which excludes PROCTOR.
        """
        gate = authorize or AuthService.can_run_match
        await AuthService.ensure(
            await gate(actor, match),
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
        message, embed = build_message(match, community, await bracket_line_for(match.id))
        discord_queue.enqueue(self.notify_match_participants(match, message, embed))
        match_live.publish(match.id)
        event_bus.publish(Event.create(event_type, {
            'match_id': match.id,
            'tournament_id': match.tournament_id,
            'tournament': match.tournament.name,
        }, actor))

    async def seat_match(self, match: Match, actor: Optional[User] = None) -> None:
        # ``check`` below is synchronous and runs before ``_transition`` fetches
        # relations, so the players have to be loaded here for it to see them.
        await match.fetch_related('tournament', 'players')
        if match.tournament and match.tournament.is_racetime_enabled:
            raise ValueError(
                "Check-in is disabled for racetime.gg tournaments — the race "
                "room manages the match lifecycle."
            )

        def check() -> None:
            if match.seated_at:
                raise ValueError("Match is already checked in")
            if not match.players:
                raise ValueError(
                    "This match has no players yet — nothing to check in."
                )
        await self._transition(
            match, actor,
            action_verb="seat",
            check=check,
            timestamp_field="seated_at",
            audit_action=AuditActions.MATCH_SEATED,
            event_type=EventType.MATCH_SEATED,
            build_message=lambda m, c, b: _checked_in_notification(m, c, b),
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
            build_message=lambda m, c, b: _state_notification(m, c, "Started", b),
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
            build_message=lambda m, c, b: _state_notification(m, c, "Finished", b),
        )

    async def confirm_match(self, match: Match, actor: Optional[User] = None) -> None:
        # ``check`` below is synchronous and runs before ``_transition`` fetches
        # relations, so the players have to be loaded here for it to see them.
        await match.fetch_related('players')

        def check() -> None:
            if not match.finished_at:
                raise ValueError("Match must be finished before confirming")
            if match.confirmed_at:
                raise ValueError("Match is already confirmed")
            if not any(p.finish_rank for p in match.players):
                raise ValueError(
                    "No result has been recorded for this match — record the "
                    "winner before confirming."
                )
        await self._transition(
            match, actor,
            action_verb="confirm",
            check=check,
            timestamp_field="confirmed_at",
            audit_action=AuditActions.MATCH_CONFIRMED,
            event_type=EventType.MATCH_CONFIRMED,
            build_message=lambda m, c, b: _state_notification(m, c, "Confirmed", b),
            authorize=AuthService.can_confirm_match,
        )

        # Confirming a flagged result *is* the resolution — the admin has now
        # looked at it, which is all the flag ever asked for. The note stays:
        # it is the record of why the result was contested. A separate
        # MATCH_REVIEW_CLEARED row (rather than extra keys on the confirm audit)
        # keeps ``_transition``'s shared detail shape untouched and makes the
        # trail read record → flag → clear → confirm.
        if match.needs_review:
            match.needs_review = False
            await match.save()
            await self.audit_service.write_and_publish(
                actor,
                AuditActions.MATCH_REVIEW_CLEARED,
                {
                    'match_id': match.id,
                    'note': match.review_note,
                    'resolved_by': 'confirmation',
                },
                EventType.MATCH_REVIEW_CLEARED,
                event_extra={'tournament_id': match.tournament_id},
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

        # Advance the native bracket when this match mirrors a bracket match.
        # Peer of the Challonge push above: fire-and-forget so a failure never
        # blocks confirmation; failures are visible via audit and manual replay.
        async def _advance_bracket_result() -> None:
            from application.services.bracket_service import BracketService
            try:
                await BracketService().advance_if_linked(match, actor)
            except Exception:  # noqa: BLE001 - logged, retried manually
                logger.exception("bracket auto-advance failed for match %s", match.id)

        discord_queue.enqueue(_advance_bracket_result())

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

                if not await AuthService.can_run_match(actor, match):
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

                # Generate the seed. A keyed randomizer resolves this community's
                # own credential inside the generator and raises when it is not
                # configured; that surfaces below as "Error generating seed: …".
                seed_url = await self.seedgen_service.generate_seed(randomizer, preset)

                # Create GeneratedSeeds record
                match.generated_seed = await GeneratedSeeds.create(
                    tournament=match.tournament,
                    seed_url=seed_url,
                    seed_info=f"Generated seed for match {match.id}"
                )
                await match.save()

                # Send DMs to players in the background (respects dm_notifications opt-out)
                descriptor = _match_descriptor(match, await bracket_line_for(match.id))
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

                match_live.publish(match.id)
                event_bus.publish(Event.create(EventType.MATCH_SEED_ROLLED, {
                    'match_id': match.id,
                    'tournament_id': match.tournament_id,
                    'seed_url': seed_url,
                }, actor))

                return True, message, seed_url

            except MissingCredentialError as e:
                # Actionable and safe to show: it names a credential this actor
                # can go and configure, never upstream response text.
                return False, str(e), None
            except Exception:
                # Log the full traceback (reaches logs + Sentry) and return a
                # generic message rather than leaking raw randomizer/HTTP error
                # text to the user and the REST 400 detail.
                logger.exception("Seed generation failed for match %s", match_id)
                return False, "Seed generation failed. Please check the server logs.", None

