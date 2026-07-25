"""Native bracket endpoints — thin routers over ``BracketService``.

Tenant- and feature-scoped by the mount (``FeatureFlag.BRACKETS``). Reads use the
any-token actor dep and stay role-agnostic (the service scopes by tenant); writes
reject read-only tokens at the HTTP layer and re-gate on Staff in the service.

The one exception is ``POST /matches/{id}/games``: ``schedule_bracket_match`` is
open to Staff, the target tournament's admin, **and** the matchup's own two
entrants — in a bracket-run tournament the bracket is the only way a player
schedules at all. It gates for itself and routes privileged callers through
``create_match`` and entrants through ``submit_match_request``; the extra
scheduling fields (stage, crew) are rejected for an entrant.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.brackets import (
    AdvanceStageRequest,
    BracketCreateRequest,
    BracketEntrantResponse,
    BracketEntryResponse,
    BracketMatchResponse,
    BracketResponse,
    BracketUpdateRequest,
    EnrollRequest,
    EntrantCreateRequest,
    LinkGameRequest,
    ReportResultRequest,
    RoundMetadataRequest,
    ScheduleGameRequest,
    SetBestOfRequest,
    SetSeedsRequest,
    StandingsGroupResponse,
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


@router.get(
    "/my-open-matches",
    response_model=List[BracketMatchResponse],
    summary="List your own open, schedulable matchups",
)
async def list_my_open_matches(
    tournament_id: Optional[int] = Query(None),
    actor: User = Depends(require_api_actor),
):
    """The caller's OPEN matchups that still have a game left to schedule.

    Only matchups whose *both* entrants are linked to a user are listed — those
    are the ones bookable into a real ``Match``.
    """
    return await BracketService().list_open_matches_for_user(actor.id, tournament_id)


@router.get(
    "/advancing-preview",
    response_model=List[BracketEntryResponse],
    summary="Preview which entries a stage advance would carry forward",
)
async def advancing_preview(
    tournament_id: int = Query(...),
    from_stage_order: int = Query(...),
    actor: User = Depends(require_api_actor),
):
    """Dry run of ``POST /brackets/advance-stage``: the source-stage entries that
    would advance, in advancement order. Writes nothing, and raises the same
    guards the real advance does.
    """
    return await BracketService().get_advancing_preview(tournament_id, from_stage_order)


@router.get(
    "/matches/{match_id}",
    response_model=BracketMatchResponse,
    summary="Get one bracket match with its series games",
)
async def get_match(match_id: int, actor: User = Depends(require_api_actor)):
    return require_found(
        await BracketService().get_match_with_games(match_id), "Bracket match"
    )


@router.get("/{bracket_id}", response_model=BracketResponse, summary="Get a bracket")
async def get_bracket(bracket_id: int, actor: User = Depends(require_api_actor)):
    return require_found(await BracketService().get_bracket(bracket_id), "Bracket")


@router.get(
    "/{bracket_id}/standings",
    response_model=List[StandingsGroupResponse],
    summary="Live standings of a round-robin or Swiss bracket",
)
async def get_standings(bracket_id: int, actor: User = Depends(require_api_actor)):
    """Points, tiebreakers and rank per entry, one entry per group.

    Round robin returns one group per pool; Swiss returns a single group.
    Elimination formats have no points table and are rejected with a 400 — read
    their placement from ``/matches`` and each entry's ``final_rank``.
    """
    return await BracketService().standings(bracket_id)


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


@router.patch("/{bracket_id}", response_model=BracketResponse, summary="Edit a DRAFT bracket")
async def update_bracket(
    bracket_id: int, body: BracketUpdateRequest, actor: User = Depends(require_write_actor)
):
    return await BracketService().update_bracket(
        actor, bracket_id, **body.model_dump(exclude_unset=True)
    )


@router.delete(
    "/{bracket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a DRAFT bracket",
)
async def delete_bracket(bracket_id: int, actor: User = Depends(require_write_actor)):
    await BracketService().delete_bracket(actor, bracket_id)


@router.put(
    "/{bracket_id}/rounds",
    response_model=BracketResponse,
    summary="Replace a bracket's per-round display metadata",
)
async def set_round_metadata(
    bracket_id: int, body: RoundMetadataRequest, actor: User = Depends(require_write_actor)
):
    return await BracketService().set_round_metadata(actor, bracket_id, body.rounds)


@router.patch(
    "/{bracket_id}/seeds",
    response_model=List[BracketEntryResponse],
    summary="Set entry seeds for a DRAFT bracket",
)
async def set_seeds(
    bracket_id: int, body: SetSeedsRequest, actor: User = Depends(require_write_actor)
):
    """Reseed in one shot: the whole resulting seeding is validated before any
    write, so a duplicate or out-of-range seed changes nothing. Returns the
    bracket's entries in their new seed order.
    """
    service = BracketService()
    await service.set_seeds(actor, bracket_id, body.seeds)
    return await service.list_entries(bracket_id)


@router.post("/entrants", response_model=BracketEntrantResponse, status_code=status.HTTP_201_CREATED, summary="Add a tournament entrant")
async def add_entrant(body: EntrantCreateRequest, actor: User = Depends(require_write_actor)):
    return await BracketService().add_entrant(
        actor,
        tournament_id=body.tournament_id,
        display_name=body.display_name,
        user_id=body.user_id,
    )


@router.post(
    "/entrants/{entrant_id}/drop",
    response_model=BracketEntrantResponse,
    summary="Drop a tournament entrant",
)
async def drop_entrant(entrant_id: int, actor: User = Depends(require_write_actor)):
    """Mark the entrant DROPPED on the tournament roster.

    Their played results stand — they keep counting for everyone else's
    standings. Note this is the *roster* state only: it does not cascade into
    their per-stage ``BracketEntry.status``, which is what stage advancement
    filters on, so a drop mid-stage still needs the entry retired separately.
    """
    return await BracketService().drop_entrant(actor, entrant_id)


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
    service = BracketService()
    await service.report_result(
        actor, match_id, body.winner_entry_id,
        entry1_score=body.entry1_score,
        entry2_score=body.entry2_score,
        forfeit=body.forfeit,
    )
    # Re-read with games loaded: the response embeds them, and report_result
    # cancels any pending game, so the caller should see that.
    return require_found(await service.get_match_with_games(match_id), "Bracket match")


@router.patch(
    "/matches/{match_id}/result",
    response_model=BracketMatchResponse,
    summary="Correct an already-reported match result",
)
async def override_result(
    match_id: int, body: ReportResultRequest, actor: User = Depends(require_write_actor)
):
    """Staff correction of a COMPLETE match's winner and scores.

    Rejected while any match downstream of this one is itself already COMPLETE —
    undo those first. On success the amended winner/loser are re-pushed into the
    downstream slots and, if the stage had already finalized, its ranks are
    recomputed from the corrected results.
    """
    service = BracketService()
    await service.override_result(
        actor, match_id, body.winner_entry_id,
        entry1_score=body.entry1_score,
        entry2_score=body.entry2_score,
        forfeit=body.forfeit,
    )
    return require_found(await service.get_match_with_games(match_id), "Bracket match")


@router.post(
    "/matches/{match_id}/games",
    response_model=BracketMatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule the next game of a match's series",
)
async def schedule_game(
    match_id: int, body: ScheduleGameRequest, actor: User = Depends(require_write_actor)
):
    """Book the next game of this matchup into a real ``Match``.

    The game number is assigned server-side — call this once per game to book a
    best-of-N, including all N slots up front. Rejected once every slot is taken
    or the series is decided.

    Staff and the tournament's admins may book on anyone's behalf; the matchup's
    two entrants may book their own. ``stream_room_id`` is staff-only, so it is
    forwarded only when actually set — an entrant sending it explicitly gets a
    400 rather than having it silently dropped.
    """
    service = BracketService()
    extra = {} if body.stream_room_id is None else {'stream_room_id': body.stream_room_id}
    await service.schedule_bracket_match(
        actor, match_id,
        scheduled_date=body.scheduled_date,
        scheduled_time=body.scheduled_time,
        comment=body.comment,
        **extra,
    )
    return require_found(await service.get_match_with_games(match_id), "Bracket match")


@router.post(
    "/matches/{match_id}/games/link",
    response_model=BracketMatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach an existing scheduled match to this matchup",
)
async def link_game(
    match_id: int, body: LinkGameRequest, actor: User = Depends(require_write_actor)
):
    """Record an already-created ``Match`` as the next game of this matchup.

    Staff / tournament admin only. The match's players must be exactly the
    matchup's two entrants, or advancement could never resolve a winner.
    """
    service = BracketService()
    await service.link_match_to_bracket_match(actor, match_id, body.scheduled_match_id)
    return require_found(await service.get_match_with_games(match_id), "Bracket match")


@router.delete(
    "/games/by-match/{scheduled_match_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach a scheduled match from its matchup",
)
async def unlink_game(
    scheduled_match_id: int, actor: User = Depends(require_write_actor)
):
    """Detach the match from its series, leaving the ``Match`` itself in place.

    Only a game that has not been played can be detached.
    """
    if not await BracketService().unlink_match(actor, scheduled_match_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That match is not linked to a bracket matchup.",
        )


@router.patch(
    "/matches/{match_id}/best-of",
    response_model=BracketMatchResponse,
    summary="Override a match's series length",
)
async def set_best_of(
    match_id: int, body: SetBestOfRequest, actor: User = Depends(require_write_actor)
):
    await BracketService().set_best_of(actor, match_id, body.best_of)
    return require_found(
        await BracketService().get_match_with_games(match_id), "Bracket match"
    )


@router.post("/{bracket_id}/complete", response_model=BracketResponse, summary="Complete a bracket stage")
async def complete_stage(bracket_id: int, actor: User = Depends(require_write_actor)):
    return await BracketService().complete_stage(actor, bracket_id)


@router.post("/advance-stage", response_model=BracketResponse, summary="Advance into the next stage")
async def advance_stage(body: AdvanceStageRequest, tournament_id: int = Query(...), actor: User = Depends(require_write_actor)):
    return await BracketService().advance_stage(actor, tournament_id, body.from_stage_order)
