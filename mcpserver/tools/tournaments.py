"""Tournament and stage reads.

Mirrors the gates on ``api/routers/tournaments.py`` and
``api/routers/stages.py``: a live token is the bar, and the tenant binding
around the call does the rest.
"""

from typing import List, Optional

from mcp.server.fastmcp import FastMCP

from api.schemas.tournaments import TournamentResponse
from application.errors import require_found
from application.services import (
    MatchSuggestionService,
    StageService,
    TournamentService,
)
from mcpserver.auth import Gate
from mcpserver.registry import register
from mcpserver.schemas import (
    MatchTimeSuggestion,
    StageInfo,
    TenantArg,
    TournamentSummary,
)


async def list_tournaments(
    tenant: TenantArg = None,
    active_only: bool = False,
) -> List[TournamentSummary]:
    """List a community's tournaments.

    Returns a compact summary per tournament; use `get_tournament` for full
    detail on one. Set `active_only` to skip finished and archived events.
    """
    tournaments = await TournamentService().get_all_tournaments(active_only=active_only)
    return [TournamentSummary.model_validate(t, from_attributes=True) for t in tournaments]


async def get_tournament(
    tournament_id: int,
    tenant: TenantArg = None,
) -> TournamentResponse:
    """Get full detail for one tournament, including its configuration."""
    tournament = require_found(
        await TournamentService().get_tournament_by_id(tournament_id), 'Tournament'
    )
    return TournamentResponse.model_validate(tournament, from_attributes=True)


async def list_stages(
    tenant: TenantArg = None,
    active_only: bool = False,
) -> List[StageInfo]:
    """List the community's stages (restream channels matches are assigned to)."""
    stages = await StageService().get_all_stages(active_only=active_only)
    return [StageInfo.model_validate(r, from_attributes=True) for r in stages]


async def get_stage(
    stage_id: int,
    tenant: TenantArg = None,
) -> StageInfo:
    """Get one stage by id."""
    stage = require_found(
        await StageService().get_stage_by_id(stage_id), 'Stage'
    )
    return StageInfo.model_validate(stage, from_attributes=True)


async def suggest_match_time(
    tournament_id: int,
    player_ids: List[int],
    tenant: TenantArg = None,
    bracket_match_id: Optional[int] = None,
) -> MatchTimeSuggestion:
    """Suggest a UTC start time for a match between the given players.

    Searches the tournament's configured hours for the slot that fits everyone's
    declared availability and adds least to the venue's concurrent load. Pass
    `bracket_match_id` to confine the search to that matchup's round window.
    Errors with `invalid_request` when no slot fits at all.
    """
    return MatchTimeSuggestion(
        suggested_at=await MatchSuggestionService().suggest_match_time(
            tournament_id, player_ids, bracket_match_id=bracket_match_id,
        )
    )


def register_tools(mcp: FastMCP) -> None:
    register(mcp, list_tournaments, gate=Gate.ACTOR, title='List tournaments')
    register(mcp, get_tournament, gate=Gate.ACTOR, title='Get tournament')
    register(mcp, list_stages, gate=Gate.ACTOR, title='List stages')
    register(mcp, get_stage, gate=Gate.ACTOR, title='Get stage')
    register(mcp, suggest_match_time, gate=Gate.ACTOR, title='Suggest a match time')
