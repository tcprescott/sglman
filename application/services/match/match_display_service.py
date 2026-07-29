"""
Match Display Service - Read/Formatting Layer

View-model assembly for the match tables: reads matches (and their
acknowledgments) via repositories and formats them into the plain dicts the
NiceGUI table slots consume. Extracted from ``MatchService`` so the latter
keeps only lifecycle logic.

Read-only: no writes, no audit, no Discord notifications.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from models import Match, MatchAcknowledgment
from application.repositories import (
    MatchAcknowledgmentRepository,
    MatchRepository,
    StreamRoomRepository,
    TournamentRepository,
)
from application.services.match.match_status import legacy_label, resolve
from application.utils.timezone import (
    format_eastern_datetime,
    format_eastern_display,
    format_eastern_time,
    to_utc_aware,
)


class MatchDisplayService:
    """Service for reading and formatting matches for table display."""

    def __init__(self) -> None:
        self.repository = MatchRepository()
        self.ack_repository = MatchAcknowledgmentRepository()
        self.tournament_repository = TournamentRepository()
        self.stream_room_repository = StreamRoomRepository()

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
        user_discord_id: Optional[str] = None,
        exclude_racetime: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get matches formatted for table display.

        Args:
            tournament_ids: Filter by tournament IDs
            stream_room_ids: Filter by stream room IDs
            only_upcoming: Only return unfinished matches
            user_discord_id: Filter by player discord ID
            exclude_racetime: Drop matches run by a racetime.gg tournament — the
                proctor board's rows are the ones a proctor can actually act on

        Returns:
            List of formatted match dictionaries
        """
        matches = await self.repository.get_all(
            tournament_ids=tournament_ids,
            stream_room_ids=stream_room_ids,
            only_upcoming=only_upcoming,
            user_discord_id=user_discord_id,
            exclude_racetime=exclude_racetime,
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

    def _get_match_state(self, match: Match) -> str:
        """The schedule table's state string for a match.

        A thin adapter over :func:`match_status.resolve` rather than its own
        ladder, so this table's labels cannot drift from the bracket's — that
        drift is exactly what made the two surfaces read as separate products.
        No ``room_status`` is passed: the schedule shows the recorded lifecycle,
        and letting a racetime room advance a row here would disagree with the
        timestamp the row's own action buttons act on.

        Returns one of the five historical strings — 'Confirmed', 'Finished',
        'Started', 'Checked In', 'Scheduled' — which the filter chips and the
        Vue table slots compare against by value.
        """
        return legacy_label(resolve(match=match))

    @staticmethod
    def _bracket_ref(match: Match) -> Optional[Dict[str, Any]]:
        """The bracket matchup this match is a game of, for the schedule's link out.

        ``bracket_match_game`` is a reverse OneToOne, so it is ``None`` for the
        vast majority of matches (nothing scheduled it through a bracket) and
        raises when the relation was not prefetched — a caller that skipped
        ``prefetch_relations`` gets no link rather than an exception.

        Beyond the stage name and game number this now carries the **series
        context** (U4): the resolved best-of and the standing so far, so a
        schedule row reads "Game 2 of 3 · 1-0" instead of a bare "Game 2". Both
        come off the games the repository already prefetched — no extra query
        per row. The round *name* is deliberately absent: naming a round is
        structural and needs the stage's whole graph, which is a query the
        schedule table must not pay per row; the Discord DMs, which fan out one
        at a time, do resolve it.
        """
        try:
            game = match.bracket_match_game
        except Exception:
            return None
        if game is None:
            return None
        bracket_match = getattr(game, 'bracket_match', None)
        bracket = getattr(bracket_match, 'bracket', None) if bracket_match else None
        if bracket is None:
            return None
        best_of, standing = MatchDisplayService._series_context(bracket, bracket_match)
        return {
            'id': bracket.id,
            'name': bracket.name,
            # Only meaningful in a best-of-N series; game 1 of 1 is just "the match".
            'game': game.game_number if game.game_number and game.game_number > 1 else None,
            'best_of': best_of,
            'standing': standing,
        }

    @staticmethod
    def _series_context(bracket, bracket_match) -> tuple:
        """``(best_of, standing)`` for a matchup, or ``(1, '')`` when unavailable.

        Both computations are the bracket service's pure ones (``resolve_best_of``
        / ``_standing_from``) reused rather than re-derived, so the schedule
        cannot quote a different series length or score than the bracket does.
        ``standing`` is '' before the first game settles — "0-0" reads as a
        result that has been played.
        """
        from application.services.bracket_service import BracketService

        try:
            best_of = BracketService.resolve_best_of(bracket, bracket_match)
            if best_of <= 1:
                return best_of, ''
            games = list(bracket_match.games)
            e1, e2 = BracketService._standing_from(games, bracket_match)
            standing = f'{max(e1, e2)}-{min(e1, e2)}' if (e1 or e2) else ''
            return best_of, standing
        except Exception:
            return 1, ''

    def _format_match_for_display(
        self,
        match: Match,
        acknowledgments: Optional[List[MatchAcknowledgment]] = None,
    ) -> Dict[str, Any]:
        """Format a match object for UI display."""
        # Get state and corresponding timestamp
        state = self._get_match_state(match)

        if match.confirmed_at:
            state_changed_at = match.confirmed_at
        elif match.finished_at:
            state_changed_at = match.finished_at
        elif match.started_at:
            state_changed_at = match.started_at
        elif match.seated_at:
            state_changed_at = match.seated_at
        else:
            state_changed_at = match.created_at
        state_timestamp = format_eastern_datetime(state_changed_at)

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
            acknowledgments_summary.append({
                'name': p.user.preferred_name,
                'acknowledged': acknowledged,
                'auto': bool(ack and ack.auto_acknowledged),
                'ts': ts_display,
                'discord_id': str(discord_id) if discord_id else None,
            })

        return {
            'id': match.id,
            'tournament': match.tournament.name if match.tournament else '',
            # None unless a bracket scheduled this match; drives the schedule's
            # link into the (publicly readable) bracket view.
            'bracket': self._bracket_ref(match),
            'scheduled_at': format_eastern_datetime(match.scheduled_at) if match.scheduled_at else '',
            # Sort key and urgency flag for the proctor board. The formatted
            # ``scheduled_at`` string is display-only and does not sort.
            'scheduled_ts': to_utc_aware(match.scheduled_at).timestamp() if match.scheduled_at else None,
            'is_overdue': bool(
                match.scheduled_at
                and match.seated_at is None
                and match.finished_at is None
                and to_utc_aware(match.scheduled_at) < datetime.now(timezone.utc)
            ),
            'state': state,
            # The proctor's dispute flag and their own words. The note outlives
            # the flag (confirming clears only the flag), so the two are
            # independent — a row can carry a note with needs_review False.
            'needs_review': match.needs_review,
            'review_note': match.review_note or '',
            'state_timestamp': state_timestamp,
            'state_time': format_eastern_time(state_changed_at),
            'players': [
                {
                    'name': p.user.preferred_name,
                    'finish_rank': p.finish_rank,
                    'station': p.assigned_station,
                    'discord_id': str(p.user.discord_id) if p.user.discord_id else None,
                }
                for p in match.players
            ],
            'acknowledgments': acknowledgments_summary,
            'stream_room': match.stream_room.name if match.stream_room else '',
            'stream_room_url': (
                match.stream_room.stream_url
                if match.stream_room and match.stream_room.stream_url
                and match.stream_room.stream_url.lower().startswith(('http://', 'https://'))
                else ''
            ),
            'is_stream_candidate': match.is_stream_candidate,
            # Online (racetime.gg) tournaments run remotely, so the table hides
            # on-site-only controls (check-in, station assignment) for their rows.
            'is_racetime': match.tournament.is_racetime_enabled if match.tournament else False,
            'seed': match.generated_seed.seed_url if match.generated_seed else '',
            'generated_seed': match.generated_seed.seed_url if match.generated_seed else '',
            'tournament_seed_generator': match.tournament.seed_generator if match.tournament else None,
            # Players the seed DM cannot reach — no linked Discord account, or
            # DMs opted out. This is deliverability, not delivery: it mirrors the
            # skip condition in ``_send_seed_dms`` and says nothing about whether
            # any DM was actually sent or read. ``players__user`` is already
            # prefetched, so this costs no extra query.
            'seed_dm_blocked': [
                p.user.preferred_name for p in match.players
                if not (p.user.discord_id and p.user.dm_notifications)
            ],
            'commentators': [
                {
                    'name': c.user.preferred_name,
                    'approved': c.approved,
                    # str: raw snowflake ints lose precision as JS numbers, breaking == checks
                    'discord_id': str(c.user.discord_id) if c.user.discord_id else None,
                    'acknowledged': c.acknowledged_at is not None,
                    'ack_ts': format_eastern_display(c.acknowledged_at) if c.acknowledged_at else '',
                    'id': c.id,
                }
                for c in match.commentators
            ],
            'trackers': [
                {
                    'name': t.user.preferred_name,
                    'approved': t.approved,
                    'discord_id': str(t.user.discord_id) if t.user.discord_id else None,
                    'acknowledged': t.acknowledged_at is not None,
                    'ack_ts': format_eastern_display(t.acknowledged_at) if t.acknowledged_at else '',
                    'id': t.id,
                }
                for t in match.trackers
            ],
            # Keep these for backward compatibility with existing code that may reference them
            'seated': format_eastern_datetime(match.seated_at) if match.seated_at else '',
            'finished': format_eastern_datetime(match.finished_at) if match.finished_at else '',
        }
