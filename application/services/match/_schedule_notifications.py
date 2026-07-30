"""Match notification mixin: the Discord DM / embed fan-out for a match.

Split out of ``match_schedule_service.py`` as pure code motion — that module had
grown past the 800-line budget after absorbing the bracket integration. Follows
the ``_bracket/`` mixin convention: ``MatchNotificationMixin`` is composed into
:class:`MatchScheduleService`, and its methods reach ``self.discord_service`` /
``self.acknowledgment_repository`` and sibling notify methods through that one
composed class, so every caller keeps using ``MatchScheduleService`` unchanged.

Every public method here is best-effort: a DM failure is logged and swallowed so
it can never block the lifecycle operation that triggered it.
"""

import logging
from typing import Optional

import discord

from application.services.discord import discord_queue
from application.services.match._dm_context import _community_name, bracket_line_for
from application.services.match._match_recipients import collect_match_recipients
from application.tenant_context import require_tenant_id
from application.utils.discord_embeds import (
    COLOR_RESCHEDULED,
    COLOR_SCHEDULED,
    COLOR_STREAM,
    match_embed,
    time_field,
)
from application.utils.discord_messages import (
    acknowledgment_request_dm,
    rescheduled_dm,
    scheduled_dm,
    stream_candidate_dm,
)
from models import Match, MatchPlayers

logger = logging.getLogger(__name__)


class MatchNotificationMixin:
    """Discord DM fan-out for match lifecycle and subscriber notifications."""

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

    async def notify_match_cancelled(
        self,
        recipients: dict[int, bool],
        message: str,
        embed: Optional[discord.Embed] = None,
    ) -> None:
        """DM a **pre-resolved** recipient set that their match was cancelled.

        Unlike every sibling notifier this takes the recipients rather than a
        ``Match``, and that difference is load-bearing. Cancellation deletes the
        row, and ``collect_match_recipients`` re-queries ``MatchPlayers`` /
        ``Commentator`` / ``Tracker`` / ``MatchWatcher`` — all of which cascade
        away with it. Because ``discord_queue`` defers this coroutine to its lone
        worker, by the time it ran the recipient set would be empty and the DMs
        would silently reach nobody. The caller resolves recipients while the
        match still exists and passes them in; this method only fans out.

        Every recipient gets a plain DM — deliberately not the watcher variant,
        whose Unwatch button would carry the id of a match that no longer exists.

        Never raises; per-DM failures are logged and swallowed.
        """
        for discord_id in recipients:
            try:
                success, err = await self.discord_service.send_dm(
                    discord_id, message, embed=embed,
                )
                if not success:
                    logger.warning(
                        "notify_match_cancelled DM failed for %s: %s", discord_id, err
                    )
            except Exception:
                logger.exception(
                    "notify_match_cancelled unexpected error for %s", discord_id
                )

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
        bracket_line: str = '',
    ) -> None:
        """
        Send a DM with an Acknowledge button to every current match player
        whose acknowledgment is still pending and who opts in to DMs.

        ``community`` is the embed-footer community name and ``bracket_line`` the
        series context, both resolved by the caller in request context — this
        coroutine is awaited later by the scope-less ``discord_queue`` worker,
        where the tenant is no longer in scope, so they must be passed in rather
        than looked up here.

        Never raises; per-DM failures are logged and swallowed.
        """
        try:
            await match.fetch_related('tournament', 'stream_room')
            scheduled_display = time_field(match.scheduled_at)
            players = await MatchPlayers.filter(match=match, tenant_id=require_tenant_id()).prefetch_related('user')
            player_names = [p.user.preferred_name for p in players]
            message = acknowledgment_request_dm(
                match.tournament.name, scheduled_display,
                rescheduled=rescheduled,
                stream_room_name=match.stream_room.name if match.stream_room else '',
                player_names=player_names,
                bracket_line=bracket_line,
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
            scheduled_display = time_field(match.scheduled_at)
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
        bracket_line = await bracket_line_for(match.id)
        msg = build_message(
            match.tournament.name,
            time_field(match.scheduled_at),
            player_names=player_names,
            stream_room_name=match.stream_room.name if match.stream_room else '',
            bracket_line=bracket_line,
        )
        community = await _community_name()
        embed = match_embed(
            title='🔄 Match rescheduled' if rescheduled else '📣 Match scheduled',
            color=COLOR_RESCHEDULED if rescheduled else COLOR_SCHEDULED,
            tournament=match.tournament.name, community_name=community,
            player_names=player_names, when=match.scheduled_at,
            stream_room_name=match.stream_room.name if match.stream_room else None,
        )
        discord_queue.enqueue(self.notify_acknowledgment_request(
            match, rescheduled=rescheduled, community=community,
            bracket_line=bracket_line,
        ))
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
