"""Native bracket endpoints — thin routers over ``BracketService``.

Tenant- and feature-scoped by the mount (``FeatureFlag.BRACKETS``). Reads use the
any-token actor dep and stay role-agnostic (the service scopes by tenant); writes
reject read-only tokens at the HTTP layer and re-gate on Staff in the service.
"""

from typing import List

from fastapi import APIRouter, Depends, Query, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.brackets import (
    AdvanceStageRequest,
    BracketCreateRequest,
    BracketEntrantResponse,
    BracketEntryResponse,
    BracketMatchResponse,
    BracketResponse,
    EnrollRequest,
    EntrantCreateRequest,
    ReportResultRequest,
)
from application.errors import require_found
from application.services import BracketService
from models import User

router = APIRouter(prefix="/brackets", tags=["Brackets"], route_class=ServiceErrorRoute)


# --- reads (any token; tenant-scoped in-service) --------------------------


@router.get("", response_model=List[BracketResponse], summary="List brackets for a tournament")
async def list_brackets(
    tournament_id: int = Query(...),
    actor: User = Depends(require_api_actor),
):
    return await BracketService().list_brackets(tournament_id)


@router.get("/entrants", response_model=List[BracketEntrantResponse], summary="List a tournament's entrants")
async def list_entrants(
    tournament_id: int = Query(...),
    actor: User = Depends(require_api_actor),
):
    return await BracketService().list_entrants(tournament_id)


@router.get("/{bracket_id}", response_model=BracketResponse, summary="Get a bracket")
async def get_bracket(bracket_id: int, actor: User = Depends(require_api_actor)):
    return require_found(await BracketService().get_bracket(bracket_id), "Bracket")


@router.get("/{bracket_id}/matches", response_model=List[BracketMatchResponse], summary="List a bracket's matches")
async def list_matches(bracket_id: int, actor: User = Depends(require_api_actor)):
    require_found(await BracketService().get_bracket(bracket_id), "Bracket")
    return await BracketService().list_matches(bracket_id)


@router.get("/{bracket_id}/open-matches", response_model=List[BracketMatchResponse], summary="List a bracket's open (playable) matches")
async def list_open_matches(bracket_id: int, actor: User = Depends(require_api_actor)):
    require_found(await BracketService().get_bracket(bracket_id), "Bracket")
    return await BracketService().get_open_matches(bracket_id)


@router.get("/{bracket_id}/entries", response_model=List[BracketEntryResponse], summary="List a bracket's entries")
async def list_entries(bracket_id: int, actor: User = Depends(require_api_actor)):
    require_found(await BracketService().get_bracket(bracket_id), "Bracket")
    return await BracketService().list_entries(bracket_id)


# --- writes (reject read-only tokens; Staff-gated in-service) --------------


@router.post("", response_model=BracketResponse, status_code=status.HTTP_201_CREATED, summary="Create a bracket")
async def create_bracket(body: BracketCreateRequest, actor: User = Depends(require_write_actor)):
    return await BracketService().create_bracket(
        actor,
        tournament_id=body.tournament_id,
        name=body.name,
        format=body.format,
        stage_order=body.stage_order,
        config=body.config,
    )


@router.post("/entrants", response_model=BracketEntrantResponse, status_code=status.HTTP_201_CREATED, summary="Add a tournament entrant")
async def add_entrant(body: EntrantCreateRequest, actor: User = Depends(require_write_actor)):
    return await BracketService().add_entrant(
        actor,
        tournament_id=body.tournament_id,
        display_name=body.display_name,
        user_id=body.user_id,
    )


@router.post("/{bracket_id}/entries", response_model=BracketEntryResponse, status_code=status.HTTP_201_CREATED, summary="Enroll an entrant into a bracket")
async def enroll(bracket_id: int, body: EnrollRequest, actor: User = Depends(require_write_actor)):
    return await BracketService().enroll(
        actor,
        bracket_id=bracket_id,
        entrant_id=body.entrant_id,
        seed=body.seed,
        group_number=body.group_number,
    )


@router.post("/{bracket_id}/start", response_model=BracketResponse, summary="Start a bracket (generate the match graph)")
async def start_bracket(bracket_id: int, actor: User = Depends(require_write_actor)):
    return await BracketService().start_bracket(actor, bracket_id)


@router.post("/matches/{match_id}/result", response_model=BracketMatchResponse, summary="Report a match result")
async def report_result(match_id: int, body: ReportResultRequest, actor: User = Depends(require_write_actor)):
    return await BracketService().report_result(actor, match_id, body.winner_entry_id)


@router.post("/{bracket_id}/complete", response_model=BracketResponse, summary="Complete a bracket stage")
async def complete_stage(bracket_id: int, actor: User = Depends(require_write_actor)):
    return await BracketService().complete_stage(actor, bracket_id)


@router.post("/advance-stage", response_model=BracketResponse, summary="Advance into the next stage")
async def advance_stage(body: AdvanceStageRequest, tournament_id: int = Query(...), actor: User = Depends(require_write_actor)):
    return await BracketService().advance_stage(actor, tournament_id, body.from_stage_order)
