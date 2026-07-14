"""Race room (racetime room lifecycle) endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import (
    ServiceErrorRoute,
    require_api_actor,
    require_staff,
    require_write_actor,
)
from api.schemas.race_rooms import (
    RaceRoomCancelRequest,
    RaceRoomCreateRequest,
    RaceRoomResponse,
    RaceRoomStatusUpdateRequest,
)
from application.services import (
    AuthService,
    MatchService,
    RaceRoomService,
    RacetimeRoomService,
)
from application.tenant_context import require_tenant_id
from models import RacetimeRoom, User

router = APIRouter(prefix="/race-rooms", tags=["Race rooms"], route_class=ServiceErrorRoute)


async def _load_room_or_404(room_id: int) -> RacetimeRoom:
    room = await RacetimeRoom.get_or_none(id=room_id, tenant_id=require_tenant_id())
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Race room not found")
    return room


# --- Reads ----------------------------------------------------------------
# Literal single-segment routes are declared before parameterized ones.

@router.get("/open", response_model=List[RaceRoomResponse], summary="List open race rooms")
async def list_open(actor: User = Depends(require_staff)):
    rooms = await RacetimeRoomService().list_open_rooms()
    tenant_id = require_tenant_id()
    return [r for r in rooms if r.tenant_id == tenant_id]


@router.get("/by-match/{match_id}", response_model=RaceRoomResponse, summary="Get the race room for a match")
async def get_by_match(match_id: int, actor: User = Depends(require_api_actor)):
    match = await MatchService().get_by_id(match_id)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    room = await RacetimeRoomService().get_for_match(match)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Race room not found")
    return room


# --- Writes ---------------------------------------------------------------

@router.post("", response_model=RaceRoomResponse, status_code=status.HTTP_201_CREATED, summary="Manually open a race room for a match")
async def create_room(payload: RaceRoomCreateRequest, actor: User = Depends(require_write_actor)):
    return await RaceRoomService().manual_create_room(actor, payload.match_id)


@router.post("/{room_id}/cancel", response_model=RaceRoomResponse, summary="Cancel a race room")
async def cancel_room(room_id: int, payload: RaceRoomCancelRequest, actor: User = Depends(require_write_actor)):
    await AuthService.ensure(
        await AuthService.can_manage_sync(actor),
        "You do not have permission to cancel a racetime room.",
    )
    room = await _load_room_or_404(room_id)
    await RaceRoomService().cancel_room(room, actor=actor, reason=payload.reason)
    return room


@router.patch("/{room_id}/status", response_model=RaceRoomResponse, summary="Set a race room's cached status")
async def set_status(room_id: int, payload: RaceRoomStatusUpdateRequest, actor: User = Depends(require_write_actor)):
    await AuthService.ensure(
        await AuthService.can_manage_sync(actor),
        "You do not have permission to change a racetime room.",
    )
    room = await _load_room_or_404(room_id)
    return await RacetimeRoomService().set_status(room, payload.status)
