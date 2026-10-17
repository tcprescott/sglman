"""Tournament endpoints."""

from typing import List

from fastapi import APIRouter, Depends, Query

from api.dependencies import ServiceErrorRoute, require_api_actor
from api.schemas.tournaments import TournamentResponse
from application.errors import require_found
from application.services import TournamentService
from models import User

router = APIRouter(
    prefix="/tournaments",
    tags=["Tournaments"],
    route_class=ServiceErrorRoute,
    dependencies=[Depends(require_api_actor)],
)


@router.get(
    "",
    response_model=List[TournamentResponse],
    summary="List tournaments",
    description=(
        "Returns this community's tournaments. Inactive tournaments are included only for "
        "admins (Staff, tournament admins and the other admin roles), and only unless you ask "
        "for active only.\n\n"
        "**Who can call this:** Any member."
    ),
)
async def list_tournaments(
    active_only: bool = Query(False, description="Return only active tournaments"),
    actor: User = Depends(require_api_actor),
):
    return await TournamentService().list_for_viewer(actor, active_only=active_only)


@router.get(
    "/{tournament_id}",
    response_model=TournamentResponse,
    summary="Get a tournament",
    description=(
        "Returns one of this community's tournaments. An inactive tournament is 404 unless "
        "you're an admin.\n\n"
        "**Who can call this:** Any member."
    ),
)
async def get_tournament(tournament_id: int, actor: User = Depends(require_api_actor)):
    return require_found(
        await TournamentService().get_for_viewer(actor, tournament_id), "Tournament"
    )
