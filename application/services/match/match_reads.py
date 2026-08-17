"""The match lookups every entry surface goes through.

Split out of ``match_service`` the way :class:`MatchReviewMixin` and
:class:`CancellationMixin` are: :class:`MatchReadsMixin` is composed into
:class:`MatchService` and reaches ``repository`` through that composed class.
Reads only — nothing here writes, audits or notifies.

They live on the service rather than being left to callers because
``pages/``, ``api/`` and ``discordbot/`` must never reach through
``match_service.repository`` for a simple read (``enforce_architecture.py``
blocks it), and because two of them are not pass-throughs at all: which
instants make up "that day" is a rule about the display clock, and grouping by
stage is the shape the board wants rather than the shape the table has.
"""

from datetime import date
from typing import Dict, List, Optional, Tuple

from application.utils.timezone import local_day_bounds
from models import Match, MatchPlayers, Stage


class MatchReadsMixin:
    """Load-or-None lookups, the schedule queries, and the stage grouping."""

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
