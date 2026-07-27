"""Tournament and stream-room reads.

Mirrors the gates on ``api/routers/tournaments.py`` and
``api/routers/stream_rooms.py``: a live token is the bar, and the tenant binding
around the call does the rest.
"""

from typing import List

from mcp.server.fastmcp import FastMCP

from api.schemas.tournaments import TournamentResponse
from application.errors import require_found
from application.services import StreamRoomService, TournamentService
from mcpserver.auth import Gate
from mcpserver.registry import register
from mcpserver.schemas import StreamRoomInfo, TenantArg, TournamentSummary


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


async def list_stream_rooms(
    tenant: TenantArg = None,
    active_only: bool = False,
) -> List[StreamRoomInfo]:
    """List the community's stream rooms (restream channels matches are assigned to)."""
    rooms = await StreamRoomService().get_all_stream_rooms(active_only=active_only)
    return [StreamRoomInfo.model_validate(r, from_attributes=True) for r in rooms]


def register_tools(mcp: FastMCP) -> None:
    register(mcp, list_tournaments, gate=Gate.ACTOR, title='List tournaments')
    register(mcp, get_tournament, gate=Gate.ACTOR, title='Get tournament')
    register(mcp, list_stream_rooms, gate=Gate.ACTOR, title='List stream rooms')
