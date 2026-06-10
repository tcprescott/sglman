"""Stream room write endpoints (Staff or Stream Manager)."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import ServiceErrorRoute, require_write_actor
from api.schemas.stream_room_actions import StreamRoomCreateRequest, StreamRoomUpdateRequest
from api.schemas.stream_rooms import StreamRoomResponse
from application.services import StreamRoomService
from models import StreamRoom, User

router = APIRouter(prefix="/stream-rooms", tags=["Stream Rooms"], route_class=ServiceErrorRoute)


async def _load_or_404(stream_room_id: int) -> StreamRoom:
    room = await StreamRoom.get_or_none(id=stream_room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stream room not found")
    return room


@router.post(
    "",
    response_model=StreamRoomResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a stream room",
)
async def create_stream_room(body: StreamRoomCreateRequest, actor: User = Depends(require_write_actor)):
    return await StreamRoomService().create_stream_room(
        name=body.name, stream_url=body.stream_url, is_active=body.is_active, actor=actor,
    )


@router.patch("/{stream_room_id}", response_model=StreamRoomResponse, summary="Update a stream room")
async def update_stream_room(
    stream_room_id: int, body: StreamRoomUpdateRequest, actor: User = Depends(require_write_actor),
):
    room = await _load_or_404(stream_room_id)
    await StreamRoomService().update_stream_room(
        room, name=body.name, stream_url=body.stream_url, is_active=body.is_active, actor=actor,
    )
    return room


@router.delete(
    "/{stream_room_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a stream room",
)
async def delete_stream_room(stream_room_id: int, actor: User = Depends(require_write_actor)):
    room = await _load_or_404(stream_room_id)
    await StreamRoomService().delete_stream_room(room, actor=actor)
