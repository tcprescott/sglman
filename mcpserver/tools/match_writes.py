"""The write surface: match management and your own participation.

Scoped to exactly what ``api/routers/match_actions.py`` exposes, tool for tool.
That is the whole rule, and it is worth stating because the alternative — adding
whichever writes seemed useful — leaves two surfaces that drift apart and a
question with no answer when the next one is proposed. A write that belongs here
belongs in the REST router too, and vice versa.

Every tool is registered at ``Gate.ACTOR``, mirroring ``require_write_actor``:
holding a live token that was approved for writing is the bar at this layer, and
the real permission check is the service's own (``can_crud_match``,
``can_run_match``, ``can_confirm_match``, ``can_assign_match_stream``). Inventing
a stricter gate here would make the two surfaces answer differently for the same
person, and the service check is the one that knows about tournament admins.

Ids are never guessed. Every tool takes ids a read tool returns — `match_id`
from `list_matches`, user ids from `list_users`, and `winner_id` from
`get_match`'s `players[].id`, which is the participation row rather than the
user.
"""

from typing import Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from api._match_view import load_match_response
from api.schemas.match_actions import SeedResultResponse
from api.schemas.matches import MatchResponse
from application.errors import require_found
from application.services import (
    CrewService,
    MatchScheduleService,
    MatchService,
    MatchWatcherService,
)
from application.tenant_context import require_tenant_id
from mcpserver.auth import Gate, current_actor
from mcpserver.registry import register
from mcpserver.schemas import OperationResult, TenantArg


async def _load_match(match_id: int):
    """Load a match in the bound community, or raise ``not_found``.

    The sanctioned load-or-404 shape for an entry surface. Hand-scoped to the
    bound tenant because a bare id from a model is otherwise a way to reach into
    another community's match.
    """
    from models import Match

    return require_found(
        await Match.get_or_none(id=match_id, tenant_id=require_tenant_id()), 'Match'
    )


async def _match_response(match_id: int) -> MatchResponse:
    return require_found(await load_match_response(match_id), 'Match')


# --- Scheduling -------------------------------------------------------------


async def create_match(
    tournament_id: int,
    scheduled_date: str,
    scheduled_time: str,
    player_ids: List[int],
    tenant: TenantArg = None,
    comment: Optional[str] = None,
    stream_room_id: Optional[int] = None,
    commentator_ids: Optional[List[int]] = None,
    tracker_ids: Optional[List[int]] = None,
    is_stream_candidate: bool = False,
) -> MatchResponse:
    """Schedule a new match and notify its players.

    `scheduled_date` is YYYY-MM-DD and `scheduled_time` is HH:MM, both read on
    the community's own clock rather than UTC. `player_ids` are Wizzrobe user
    ids from `list_users`. Returns the created match.
    """
    actor = current_actor().user
    match = await MatchService().create_match(
        tournament_id=tournament_id,
        scheduled_date=scheduled_date,
        scheduled_time=scheduled_time,
        player_ids=player_ids,
        comment=comment,
        stream_room_id=stream_room_id,
        commentator_ids=commentator_ids,
        tracker_ids=tracker_ids,
        is_stream_candidate=is_stream_candidate,
        actor=actor,
    )
    return await _match_response(match.id)


async def submit_match_request(
    tournament_id: int,
    scheduled_date: str,
    scheduled_time: str,
    player_ids: List[int],
    tenant: TenantArg = None,
    comment: Optional[str] = None,
) -> MatchResponse:
    """Propose a match as one of its players, for staff to approve.

    The player-initiated path: you must be among `player_ids`. Use `create_match`
    instead when you hold the role to schedule directly. Dates and times are on
    the community's clock.
    """
    actor = current_actor().user
    match = await MatchService().submit_match_request(
        tournament_id=tournament_id,
        scheduled_date=scheduled_date,
        scheduled_time=scheduled_time,
        player_ids=player_ids,
        actor=actor,
        comment=comment,
    )
    return await _match_response(match.id)


async def update_match(
    match_id: int,
    tenant: TenantArg = None,
    tournament_id: Optional[int] = None,
    scheduled_date: Optional[str] = None,
    scheduled_time: Optional[str] = None,
    player_ids: Optional[List[int]] = None,
    commentator_ids: Optional[List[int]] = None,
    tracker_ids: Optional[List[int]] = None,
    comment: Optional[str] = None,
    clear_seated: bool = False,
    clear_started: bool = False,
    clear_finished: bool = False,
    clear_confirmed: bool = False,
    clear_seed: bool = False,
) -> MatchResponse:
    """Change a scheduled match: time, tournament, players, crew or comment.

    Only the arguments you pass are changed. The `clear_*` flags roll back a
    lifecycle step that was reached in error — clearing a later step does not
    clear the earlier ones for you. Rescheduling re-notifies the players.
    """
    actor = current_actor().user
    await MatchService().update_match(
        match_id,
        tournament_id=tournament_id,
        scheduled_date=scheduled_date,
        scheduled_time=scheduled_time,
        player_ids=player_ids,
        commentator_ids=commentator_ids,
        tracker_ids=tracker_ids,
        comment=comment,
        clear_seated=clear_seated,
        clear_started=clear_started,
        clear_finished=clear_finished,
        clear_confirmed=clear_confirmed,
        clear_seed=clear_seed,
        actor=actor,
    )
    return await _match_response(match_id)


async def delete_match(
    match_id: int,
    tenant: TenantArg = None,
) -> OperationResult:
    """Delete a match. This cannot be undone — confirm with the user first.

    Players and crew are notified that it is off.
    """
    actor = current_actor().user
    await MatchService().delete_match(match_id, actor=actor)
    return OperationResult(detail=f'Match {match_id} deleted.')


# --- Stream and stations ----------------------------------------------------


async def set_match_stream_candidate(
    match_id: int,
    flag: bool,
    tenant: TenantArg = None,
) -> MatchResponse:
    """Mark a match as a restream candidate, or drop the mark."""
    actor = current_actor().user
    await MatchService().set_stream_candidate(match_id, flag, actor=actor)
    return await _match_response(match_id)


async def assign_match_stream_room(
    match_id: int,
    tenant: TenantArg = None,
    stream_room_id: Optional[int] = None,
) -> MatchResponse:
    """Put a match in a stream room, or take it out.

    `stream_room_id` comes from `list_stream_rooms`; omit it to clear the room.
    """
    actor = current_actor().user
    await MatchService().assign_stage(match_id, stream_room_id, actor=actor)
    return await _match_response(match_id)


async def assign_match_stations(
    match_id: int,
    assignments: Dict[int, Optional[str]],
    tenant: TenantArg = None,
) -> MatchResponse:
    """Set which station each player is on.

    `assignments` maps a participation row id — `get_match`'s `players[].id`,
    not a user id — to a station label, or to null to clear it.
    """
    actor = current_actor().user
    await MatchService().assign_stations(match_id, assignments, actor=actor)
    return await _match_response(match_id)


# --- Lifecycle --------------------------------------------------------------


async def seat_match(
    match_id: int,
    tenant: TenantArg = None,
) -> MatchResponse:
    """Check a match in. The first lifecycle step, before starting it."""
    actor = current_actor().user
    await MatchScheduleService().seat_match(await _load_match(match_id), actor=actor)
    return await _match_response(match_id)


async def start_match(
    match_id: int,
    tenant: TenantArg = None,
) -> MatchResponse:
    """Start a match. It must be checked in first."""
    actor = current_actor().user
    await MatchScheduleService().start_match(await _load_match(match_id), actor=actor)
    return await _match_response(match_id)


async def finish_match(
    match_id: int,
    tenant: TenantArg = None,
) -> MatchResponse:
    """Finish a match. It must be started first."""
    actor = current_actor().user
    await MatchScheduleService().finish_match(await _load_match(match_id), actor=actor)
    return await _match_response(match_id)


async def confirm_match(
    match_id: int,
    tenant: TenantArg = None,
) -> MatchResponse:
    """Confirm a finished match, closing it out.

    It must be finished and have a recorded result. Confirming also clears any
    review flag.
    """
    actor = current_actor().user
    await MatchScheduleService().confirm_match(await _load_match(match_id), actor=actor)
    return await _match_response(match_id)


async def record_match_result(
    match_id: int,
    winner_id: int,
    tenant: TenantArg = None,
) -> MatchResponse:
    """Record who won a two-player match.

    `winner_id` is the winner's participation row id — `get_match`'s
    `players[].id` — not their user id. Read the match first rather than
    guessing which of the two it is.
    """
    actor = current_actor().user
    await MatchService().record_match_result(match_id, winner_id, actor=actor)
    return await _match_response(match_id)


async def set_match_review(
    match_id: int,
    needs_review: bool,
    tenant: TenantArg = None,
    note: Optional[str] = None,
) -> MatchResponse:
    """Flag a recorded result as contested, or clear the flag.

    Raising the flag is the proctor's call and takes a `note` saying what is
    disputed; clearing it is an admin's, and keeps the note as the record.
    """
    actor = current_actor().user
    service = MatchService()
    if needs_review:
        await service.flag_for_review(match_id, note, actor=actor)
    else:
        await service.clear_review(match_id, actor=actor)
    return await _match_response(match_id)


async def generate_match_seed(
    match_id: int,
    tenant: TenantArg = None,
) -> SeedResultResponse:
    """Roll the seed for a match and DM it to the players.

    Uses the tournament's configured randomizer and preset. Refuses while a
    generation for the same match is already running.
    """
    actor = current_actor().user
    success, message, seed_url = await MatchScheduleService().generate_seed(
        match_id, actor=actor
    )
    if not success:
        raise ValueError(message)
    return SeedResultResponse(message=message, seed_url=seed_url)


# --- Your own participation -------------------------------------------------


async def signup_as_crew(
    match_id: int,
    role: str,
    tenant: TenantArg = None,
) -> OperationResult:
    """Sign yourself up to crew a match as `commentator` or `tracker`.

    Signs up the person this connection belongs to, never anyone else. The
    signup may need staff approval before it counts.
    """
    actor = current_actor().user
    await CrewService().signup_crew(match_id, actor, role)
    return OperationResult(detail=f'Signed up as {role} for match {match_id}.')


async def withdraw_crew_signup(
    match_id: int,
    role: str,
    tenant: TenantArg = None,
) -> OperationResult:
    """Withdraw your own `commentator` or `tracker` signup from a match."""
    actor = current_actor().user
    await CrewService().undo_crew_signup(match_id, actor, role)
    return OperationResult(detail=f'Withdrew your {role} signup for match {match_id}.')


async def acknowledge_match(
    match_id: int,
    tenant: TenantArg = None,
) -> OperationResult:
    """Acknowledge a match you are playing in, confirming you know about it.

    Only a player of the match can acknowledge it, and only once.
    """
    actor = current_actor().user
    await MatchService().acknowledge_match(match_id, actor)
    return OperationResult(detail=f'Acknowledged match {match_id}.')


async def watch_match(
    match_id: int,
    tenant: TenantArg = None,
) -> OperationResult:
    """Get DMs when a match you are not in changes. Not available once confirmed."""
    actor = current_actor().user
    await MatchWatcherService().watch(match_id, actor)
    return OperationResult(detail=f'Watching match {match_id}.')


async def unwatch_match(
    match_id: int,
    tenant: TenantArg = None,
) -> OperationResult:
    """Stop getting updates about a match you were watching."""
    actor = current_actor().user
    removed = await MatchWatcherService().unwatch(match_id, actor)
    return OperationResult(
        ok=removed,
        detail=(
            f'No longer watching match {match_id}.' if removed
            else f'You were not watching match {match_id}.'
        ),
    )


def register_tools(mcp: FastMCP) -> None:
    write = {'gate': Gate.ACTOR, 'write': True}
    register(mcp, create_match, title='Create match', **write)
    register(mcp, submit_match_request, title='Request match', **write)
    register(mcp, update_match, title='Update match', **write)
    register(mcp, delete_match, title='Delete match', destructive=True, **write)
    register(
        mcp, set_match_stream_candidate, title='Set stream candidate', **write,
    )
    register(mcp, assign_match_stream_room, title='Assign stream room', **write)
    register(mcp, assign_match_stations, title='Assign stations', **write)
    register(mcp, seat_match, title='Check in match', **write)
    register(mcp, start_match, title='Start match', **write)
    register(mcp, finish_match, title='Finish match', **write)
    register(mcp, confirm_match, title='Confirm match', **write)
    register(mcp, record_match_result, title='Record result', **write)
    register(mcp, set_match_review, title='Flag or clear review', **write)
    register(mcp, generate_match_seed, title='Generate seed', **write)
    register(mcp, signup_as_crew, title='Sign up as crew', **write)
    register(
        mcp, withdraw_crew_signup, title='Withdraw crew signup',
        destructive=True, **write,
    )
    register(mcp, acknowledge_match, title='Acknowledge match', **write)
    register(mcp, watch_match, title='Watch match', **write)
    register(mcp, unwatch_match, title='Stop watching match', **write)
