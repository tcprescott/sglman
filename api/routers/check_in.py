"""Check-in desk endpoints: the roster, checking people in, links and walk-ups.

Gated by the ``EVENT_CHECK_IN`` feature flag at the router and again inside
``CheckInService`` (and ``CheckInDeskService`` for the reads). The HTTP layer takes the coarse read/write token gate and
lets the service answer who may do what, so the rules match the desk page
exactly: staff and Check-in Desk volunteers work the desk, only staff add
walk-ups or check in someone who no longer holds a badge, and a desk
volunteer sees only open events.

Event setup (venues, comp rules, badge lanyards) stays in Admin → Check-in.
"""

from typing import List

from fastapi import APIRouter, Depends, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.check_in import (
    CheckInEntrantResponse,
    CheckInEventResponse,
    CheckInRequest,
    CheckInResultResponse,
    CheckInSyncResponse,
    LinkEntrantRequest,
    WalkUpRequest,
)
from application.errors import require_found
from application.services import CheckInDeskService, CheckInService
from models import User

router = APIRouter(prefix="/check-in", tags=["Check-in"], route_class=ServiceErrorRoute)


async def _entrant_response(service: CheckInService, entrant_id: int) -> CheckInEntrantResponse:
    """Re-read a row after a write so the response carries its badges and names."""
    entrant = require_found(await service.get_entrant(entrant_id), 'Roster entry')
    return CheckInEntrantResponse.from_row(entrant, await service.volunteer_user_ids())


@router.get(
    "/events",
    response_model=List[CheckInEventResponse],
    summary="List the check-in events you can work",
)
async def list_events(actor: User = Depends(require_api_actor)):
    return [CheckInEventResponse.from_row(e) for e in await CheckInDeskService().events_for(actor)]


@router.get(
    "/events/{event_id}/roster",
    response_model=List[CheckInEntrantResponse],
    summary="An event's roster, with each person's badges, lanyard and check-in state",
)
async def get_roster(event_id: int, actor: User = Depends(require_api_actor)):
    service = CheckInService()
    _, entrants = await CheckInDeskService().roster_for(actor, event_id)
    volunteers = await service.volunteer_user_ids()
    return [CheckInEntrantResponse.from_row(e, volunteers) for e in entrants]


@router.post(
    "/events/{event_id}/sync",
    response_model=CheckInSyncResponse,
    summary="Pull the latest badge sales and comps into the roster",
)
async def sync_event(event_id: int, actor: User = Depends(require_write_actor)):
    result = await CheckInService().sync_event(actor, event_id)
    return CheckInSyncResponse(**result.as_dict())


@router.post(
    "/events/{event_id}/walk-ups",
    response_model=CheckInEntrantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add someone who didn't buy a badge (Staff only)",
)
async def add_walk_up(event_id: int, body: WalkUpRequest, actor: User = Depends(require_write_actor)):
    service = CheckInService()
    entrant = await service.add_walk_up(
        actor, event_id, user_id=body.user_id, name=body.name, check_in=body.check_in,
    )
    return await _entrant_response(service, entrant.id)


@router.post(
    "/entrants/{entrant_id}/check-in",
    response_model=CheckInResultResponse,
    summary="Check someone in",
    description=(
        "Checking in someone already checked in changes nothing and returns `already: true`. "
        "Someone withdrawn (refunded, no badge left) is refused unless a staff caller sends "
        "`despite_withdrawn: true`."
    ),
)
async def check_in(
    entrant_id: int,
    body: CheckInRequest | None = None,
    actor: User = Depends(require_write_actor),
):
    service = CheckInService()
    outcome = await service.check_in(
        actor, entrant_id, despite_withdrawn=bool(body and body.despite_withdrawn),
    )
    return CheckInResultResponse(
        entrant=await _entrant_response(service, outcome.entrant.id), already=outcome.already,
    )


@router.delete(
    "/entrants/{entrant_id}/check-in",
    response_model=CheckInEntrantResponse,
    summary="Undo a check-in",
)
async def undo_check_in(entrant_id: int, actor: User = Depends(require_write_actor)):
    service = CheckInService()
    await service.undo_check_in(actor, entrant_id)
    return await _entrant_response(service, entrant_id)


@router.put(
    "/entrants/{entrant_id}/user",
    response_model=CheckInEntrantResponse,
    summary="Link a roster row to a member's account",
)
async def link_entrant(
    entrant_id: int, body: LinkEntrantRequest, actor: User = Depends(require_write_actor),
):
    service = CheckInService()
    await service.link(actor, entrant_id, body.user_id)
    return await _entrant_response(service, entrant_id)


@router.delete(
    "/entrants/{entrant_id}/user",
    response_model=CheckInEntrantResponse,
    summary="Unlink a roster row from its account",
)
async def unlink_entrant(entrant_id: int, actor: User = Depends(require_write_actor)):
    service = CheckInService()
    await service.unlink(actor, entrant_id)
    return await _entrant_response(service, entrant_id)
