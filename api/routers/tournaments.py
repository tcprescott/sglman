"""Tournament endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import ServiceErrorRoute, require_api_actor
from api.schemas.tournaments import TournamentResponse
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
    tournament = await TournamentService().get_tournament_by_id(tournament_id)
    if tournament is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tournament not found")
    return tournament
