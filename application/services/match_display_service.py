"""
Match Display Service - Read/Formatting Layer

View-model assembly for the match tables: reads matches (and their
acknowledgments) via repositories and formats them into the plain dicts the
NiceGUI table slots consume. Extracted from ``MatchService`` so the latter
keeps only lifecycle logic.

Read-only: no writes, no audit, no Discord notifications.
"""

from typing import List, Optional, Dict, Any

from models import Match, MatchAcknowledgment
from application.repositories import (
    MatchAcknowledgmentRepository,
    MatchRepository,
    StreamRoomRepository,
    TournamentRepository,
)
from application.utils.timezone import (
    format_eastern_datetime,
    format_eastern_display,
    format_eastern_time,
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
            'scheduled_at': format_eastern_datetime(match.scheduled_at) if match.scheduled_at else '',
            'state': state,
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
            'seed': match.generated_seed.seed_url if match.generated_seed else '',
            'generated_seed': match.generated_seed.seed_url if match.generated_seed else '',
            'tournament_seed_generator': match.tournament.seed_generator if match.tournament else None,
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
