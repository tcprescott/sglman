"""Match write endpoints.

Every route delegates to the service layer, which enforces permissions, writes
audit logs, and queues Discord notifications. Service ``PermissionError`` /
``ValueError`` are mapped to 403 / 400 by ``ServiceErrorRoute``.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from api._match_view import load_match_response
from api.dependencies import ServiceErrorRoute, require_write_actor
from api.schemas.match_actions import (
    AssignStageRequest,
    AssignStationsRequest,
    CrewSignupRequest,
    MatchCreateRequest,
    MatchRequestCreate,
    MatchUpdateRequest,
    RecordResultRequest,
    SeedResultResponse,
    StreamCandidateRequest,
)
from api.schemas.matches import MatchResponse
from application.errors import require_found
from application.services import CrewService, MatchScheduleService, MatchService, MatchWatcherService
from application.tenant_context import require_tenant_id
from models import Match, User

router = APIRouter(prefix="/matches", tags=["Matches"], route_class=ServiceErrorRoute)


async def _load_match_or_404(match_id: int) -> Match:
    return require_found(
        await Match.get_or_none(id=match_id, tenant_id=require_tenant_id()), "Match"
    )


@router.post("", response_model=MatchResponse, status_code=status.HTTP_201_CREATED, summary="Create a match")
async def create_match(body: MatchCreateRequest, actor: User = Depends(require_write_actor)):
    match = await MatchService().create_match(
        tournament_id=body.tournament_id,
        scheduled_date=body.scheduled_date,
        scheduled_time=body.scheduled_time,
        player_ids=body.player_ids,
        comment=body.comment,
        stream_room_id=body.stream_room_id,
        commentator_ids=body.commentator_ids,
        tracker_ids=body.tracker_ids,
        is_stream_candidate=body.is_stream_candidate,
        actor=actor,
    )
    return await load_match_response(match.id)


@router.post(
    "/request",
    response_model=MatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a match request (player-initiated)",
)
async def submit_match_request(body: MatchRequestCreate, actor: User = Depends(require_write_actor)):
    match = await MatchService().submit_match_request(
        tournament_id=body.tournament_id,
        scheduled_date=body.scheduled_date,
        scheduled_time=body.scheduled_time,
        player_ids=body.player_ids,
        actor=actor,
        comment=body.comment,
    )
    return await load_match_response(match.id)


@router.patch("/{match_id}", response_model=MatchResponse, summary="Update a match")
async def update_match(match_id: int, body: MatchUpdateRequest, actor: User = Depends(require_write_actor)):
    await MatchService().update_match(
        match_id,
        tournament_id=body.tournament_id,
        scheduled_date=body.scheduled_date,
        scheduled_time=body.scheduled_time,
        player_ids=body.player_ids,
        commentator_ids=body.commentator_ids,
        tracker_ids=body.tracker_ids,
        comment=body.comment,
        clear_seated=body.clear_seated,
        clear_started=body.clear_started,
        clear_finished=body.clear_finished,
        clear_confirmed=body.clear_confirmed,
        clear_seed=body.clear_seed,
        actor=actor,
    )
    return await load_match_response(match_id)


@router.delete("/{match_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a match")
async def delete_match(match_id: int, actor: User = Depends(require_write_actor)):
    await MatchService().delete_match(match_id, actor=actor)


@router.post("/{match_id}/stream-candidate", response_model=MatchResponse, summary="Set/clear stream candidate")
async def set_stream_candidate(match_id: int, body: StreamCandidateRequest, actor: User = Depends(require_write_actor)):
    await MatchService().set_stream_candidate(match_id, body.flag, actor=actor)
    return await load_match_response(match_id)


@router.post("/{match_id}/stage", response_model=MatchResponse, summary="Assign or clear the stream room")
async def assign_stage(match_id: int, body: AssignStageRequest, actor: User = Depends(require_write_actor)):
    await MatchService().assign_stage(match_id, body.stream_room_id, actor=actor)
    return await load_match_response(match_id)


@router.post("/{match_id}/stations", response_model=MatchResponse, summary="Assign player stations")
async def assign_stations(match_id: int, body: AssignStationsRequest, actor: User = Depends(require_write_actor)):
    await MatchService().assign_stations(match_id, body.assignments, actor=actor)
    return await load_match_response(match_id)


@router.post("/{match_id}/seat", response_model=MatchResponse, summary="Check in (seat) a match")
async def seat_match(match_id: int, actor: User = Depends(require_write_actor)):
    match = await _load_match_or_404(match_id)
    await MatchScheduleService().seat_match(match, actor=actor)
    return await load_match_response(match_id)


@router.post("/{match_id}/start", response_model=MatchResponse, summary="Start a match")
async def start_match(match_id: int, actor: User = Depends(require_write_actor)):
    match = await _load_match_or_404(match_id)
    await MatchScheduleService().start_match(match, actor=actor)
    return await load_match_response(match_id)


@router.post("/{match_id}/finish", response_model=MatchResponse, summary="Finish a match")
async def finish_match(match_id: int, actor: User = Depends(require_write_actor)):
    match = await _load_match_or_404(match_id)
    await MatchScheduleService().finish_match(match, actor=actor)
    return await load_match_response(match_id)


@router.post("/{match_id}/confirm", response_model=MatchResponse, summary="Confirm a match")
async def confirm_match(match_id: int, actor: User = Depends(require_write_actor)):
    match = await _load_match_or_404(match_id)
    await MatchScheduleService().confirm_match(match, actor=actor)
    return await load_match_response(match_id)


@router.post("/{match_id}/result", response_model=MatchResponse, summary="Record a match result")
async def record_result(match_id: int, body: RecordResultRequest, actor: User = Depends(require_write_actor)):
    await MatchService().record_match_result(match_id, body.winner_id, actor=actor)
    return await load_match_response(match_id)


@router.post("/{match_id}/seed", response_model=SeedResultResponse, summary="Generate a seed for a match")
async def generate_seed(match_id: int, actor: User = Depends(require_write_actor)):
    success, message, seed_url = await MatchScheduleService().generate_seed(match_id, actor=actor)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return SeedResultResponse(message=message, seed_url=seed_url)


@router.post("/{match_id}/crew", status_code=status.HTTP_201_CREATED, summary="Sign yourself up as crew")
async def signup_crew(match_id: int, body: CrewSignupRequest, actor: User = Depends(require_write_actor)):
    await CrewService().signup_crew(match_id, actor, body.role)
    return {"detail": f"Signed up as {body.role}"}


@router.delete("/{match_id}/crew/{role}", status_code=status.HTTP_204_NO_CONTENT, summary="Undo your crew signup")
async def undo_crew_signup(match_id: int, role: str, actor: User = Depends(require_write_actor)):
    await CrewService().undo_crew_signup(match_id, actor, role)


@router.post("/{match_id}/acknowledge", status_code=status.HTTP_200_OK, summary="Acknowledge your match")
async def acknowledge_match(match_id: int, actor: User = Depends(require_write_actor)):
    await MatchService().acknowledge_match(match_id, actor)
    return {"detail": "Match acknowledged"}


@router.post("/{match_id}/watch", status_code=status.HTTP_200_OK, summary="Watch a match for updates")
async def watch_match(match_id: int, actor: User = Depends(require_write_actor)):
    await MatchWatcherService().watch(match_id, actor)
    return {"detail": "Watching match"}


@router.delete("/{match_id}/watch", status_code=status.HTTP_204_NO_CONTENT, summary="Stop watching a match")
async def unwatch_match(match_id: int, actor: User = Depends(require_write_actor)):
    await MatchWatcherService().unwatch(match_id, actor)
