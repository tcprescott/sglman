"""Tournament write endpoints (create/update/delete, admin & crew-coordinator membership)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.match_actions import MatchSuggestionResponse
from api.schemas.tournament_actions import (
    MembershipRequest,
    TournamentCreateRequest,
    TournamentUpdateRequest,
)
from api.schemas.tournaments import TournamentResponse
from application.services import MatchSuggestionService, TournamentService, UserService
from models import Tournament, User

router = APIRouter(prefix="/tournaments", tags=["Tournaments"], route_class=ServiceErrorRoute)


async def _load_tournament_or_404(tournament_id: int) -> Tournament:
    tournament = await Tournament.get_or_none(id=tournament_id)
    if tournament is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tournament not found")
    return tournament


async def _load_user_or_404(user_id: int) -> User:
    user = await UserService().get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post(
    "",
    response_model=TournamentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tournament (Staff only)",
)
async def create_tournament(body: TournamentCreateRequest, actor: User = Depends(require_write_actor)):
    return await TournamentService().create_tournament(actor=actor, **body.model_dump())


@router.patch(
    "/{tournament_id}",
    response_model=TournamentResponse,
    summary="Update a tournament (Staff or Tournament Admin)",
)
async def update_tournament(
    tournament_id: int, body: TournamentUpdateRequest, actor: User = Depends(require_write_actor),
):
    tournament = await _load_tournament_or_404(tournament_id)
    # The repository mutates ``tournament`` in place (and returns None), so we
    # return the now-updated instance.
    await TournamentService().update_tournament(
        tournament, actor=actor, **body.model_dump(exclude_unset=True),
    )
    return tournament


@router.delete(
    "/{tournament_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tournament (Staff only)",
)
async def delete_tournament(tournament_id: int, actor: User = Depends(require_write_actor)):
    tournament = await _load_tournament_or_404(tournament_id)
    await TournamentService().delete_tournament(tournament, actor=actor)


@router.get(
    "/{tournament_id}/match-suggestion",
    response_model=MatchSuggestionResponse,
    summary="Suggest a match start time for the given players",
)
async def suggest_match_time(
    tournament_id: int,
    player_ids: List[int] = Query(..., description="User IDs of the players"),
    actor: User = Depends(require_api_actor),
):
    suggested_at = await MatchSuggestionService().suggest_match_time(tournament_id, player_ids)
    return MatchSuggestionResponse(suggested_at=suggested_at)


@router.post("/{tournament_id}/admins", summary="Add a tournament admin (Staff only)")
async def add_admin(tournament_id: int, body: MembershipRequest, actor: User = Depends(require_write_actor)):
    tournament = await _load_tournament_or_404(tournament_id)
    target = await _load_user_or_404(body.user_id)
    await TournamentService().add_admin(tournament, target, actor=actor)
    return {"detail": "Admin added"}


@router.delete(
    "/{tournament_id}/admins/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a tournament admin (Staff only)",
)
async def remove_admin(tournament_id: int, user_id: int, actor: User = Depends(require_write_actor)):
    tournament = await _load_tournament_or_404(tournament_id)
    target = await _load_user_or_404(user_id)
    await TournamentService().remove_admin(tournament, target, actor=actor)


@router.post("/{tournament_id}/crew-coordinators", summary="Add a crew coordinator (Staff only)")
async def add_crew_coordinator(
    tournament_id: int, body: MembershipRequest, actor: User = Depends(require_write_actor),
):
    tournament = await _load_tournament_or_404(tournament_id)
    target = await _load_user_or_404(body.user_id)
    await TournamentService().add_crew_coordinator(tournament, target, actor=actor)
    return {"detail": "Crew coordinator added"}


@router.delete(
    "/{tournament_id}/crew-coordinators/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a crew coordinator (Staff only)",
)
async def remove_crew_coordinator(
    tournament_id: int, user_id: int, actor: User = Depends(require_write_actor),
):
    tournament = await _load_tournament_or_404(tournament_id)
    target = await _load_user_or_404(user_id)
    await TournamentService().remove_crew_coordinator(tournament, target, actor=actor)
