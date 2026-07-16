"""Tournament endpoints."""

from typing import List

from fastapi import APIRouter, Depends, Query

from api.dependencies import ServiceErrorRoute, require_api_actor
from api.schemas.tournaments import TournamentResponse
from application.errors import require_found
from application.services import TournamentService

router = APIRouter(
    prefix="/tournaments",
    tags=["Tournaments"],
    route_class=ServiceErrorRoute,
    dependencies=[Depends(require_api_actor)],
)


@router.get("", response_model=List[TournamentResponse], summary="List tournaments")
async def list_tournaments(
    active_only: bool = Query(False, description="Return only active tournaments"),
):
    return await TournamentService().get_all_tournaments(active_only=active_only)


@router.get("/{tournament_id}", response_model=TournamentResponse, summary="Get a tournament")
async def get_tournament(tournament_id: int):
    return require_found(
        await TournamentService().get_tournament_by_id(tournament_id), "Tournament"
    )
