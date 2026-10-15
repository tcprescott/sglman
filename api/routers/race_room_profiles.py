"""Race room profile endpoints — reusable racetime room settings (SYNC_ADMIN)."""

from typing import List

from fastapi import APIRouter, Depends, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.race_room_profiles import (
    RaceRoomProfileCreateRequest,
    RaceRoomProfileResponse,
    RaceRoomProfileUpdateRequest,
)
from application.services import RaceRoomProfileService
from models import User

router = APIRouter(prefix="/race-room-profiles", tags=["Race room profiles"], route_class=ServiceErrorRoute)


@router.get(
    "",
    response_model=List[RaceRoomProfileResponse],
    summary="List race room profiles",
    description=(
        "Lists this community's race room profiles: shared racetime.gg room settings a "
        "tournament can point at.\n\n"
        "**Who can call this:** Staff or Sync admin."
    ),
)
async def list_profiles(actor: User = Depends(require_api_actor)):
    return await RaceRoomProfileService().list_profiles(actor)


@router.get(
    "/selectable",
    response_model=List[RaceRoomProfileResponse],
    summary="List profiles selectable for a tournament",
    description=(
        "Lists every profile, for choosing one on a tournament. The same rows as `GET "
        "/race-room-profiles`, open to every member.\n\n"
        "**Who can call this:** Any member."
    ),
)
async def list_selectable(actor: User = Depends(require_api_actor)):
    return await RaceRoomProfileService().list_selectable()


@router.get(
    "/{profile_id}",
    response_model=RaceRoomProfileResponse,
    summary="Get a race room profile",
    description="Returns one profile.\n\n**Who can call this:** Staff or Sync admin.",
)
async def get_profile(profile_id: int, actor: User = Depends(require_api_actor)):
    return await RaceRoomProfileService().get_profile(actor, profile_id)


@router.post(
    "",
    response_model=RaceRoomProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a race room profile",
    description=(
        "Creates a profile. Settings you leave out take the defaults noted on the request "
        "fields. Fails with 400 when the name is empty or already used, or a number is "
        "negative.\n\n"
        "**Who can call this:** Staff or Sync admin."
    ),
)
async def create_profile(body: RaceRoomProfileCreateRequest, actor: User = Depends(require_write_actor)):
    data = body.model_dump(exclude_unset=True)
    name = data.pop("name")
    return await RaceRoomProfileService().create_profile(actor, name=name, **data)


@router.patch(
    "/{profile_id}",
    response_model=RaceRoomProfileResponse,
    summary="Update a race room profile",
    description=(
        "Edits a profile; omitted fields keep their value. Rooms already open keep the "
        "settings they opened with. Fails with 400 when the name is empty or already used, or "
        "a number is negative.\n\n"
        "**Who can call this:** Staff or Sync admin."
    ),
)
async def update_profile(profile_id: int, body: RaceRoomProfileUpdateRequest, actor: User = Depends(require_write_actor)):
    return await RaceRoomProfileService().update_profile(actor, profile_id, **body.model_dump(exclude_unset=True))


@router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a race room profile",
    description=(
        "Deletes a profile. Tournaments that used it fall back to their own racetime goal.\n\n"
        "**Who can call this:** Staff or Sync admin."
    ),
)
async def delete_profile(profile_id: int, actor: User = Depends(require_write_actor)):
    await RaceRoomProfileService().delete_profile(actor, profile_id)
