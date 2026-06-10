"""Stream room endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import ServiceErrorRoute, require_api_actor
from api.schemas.stream_rooms import StreamRoomResponse
from application.services import StreamRoomService

router = APIRouter(
    prefix="/stream-rooms",
    tags=["Stream Rooms"],
    route_class=ServiceErrorRoute,
    dependencies=[Depends(require_api_actor)],
)


@router.get("", response_model=List[StreamRoomResponse], summary="List stream rooms")
async def list_stream_rooms(
    active_only: bool = Query(False, description="Return only active stream rooms"),
):
    return await StreamRoomService().get_all_stream_rooms(active_only=active_only)


@router.get("/{stream_room_id}", response_model=StreamRoomResponse, summary="Get a stream room")
async def get_stream_room(stream_room_id: int):
    room = await StreamRoomService().get_stream_room_by_id(stream_room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stream room not found")
    return room
