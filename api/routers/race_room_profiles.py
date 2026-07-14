"""Race room profile endpoints — reusable racetime room settings (SYNC_ADMIN)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.race_room_profiles import (
    RaceRoomProfileCreateRequest,
    RaceRoomProfileResponse,
    RaceRoomProfileUpdateRequest,
)
from application.services import RaceRoomProfileService
from application.tenant_context import require_tenant_id
from models import RaceRoomProfile, User

router = APIRouter(prefix="/race-room-profiles", tags=["Race room profiles"], route_class=ServiceErrorRoute)


async def _load_or_404(profile_id: int) -> RaceRoomProfile:
    profile = await RaceRoomProfile.get_or_none(id=profile_id, tenant_id=require_tenant_id())
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Race room profile not found")
    return profile


@router.get("", response_model=List[RaceRoomProfileResponse], summary="List race room profiles")
async def list_profiles(actor: User = Depends(require_api_actor)):
    return await RaceRoomProfileService().list_profiles(actor)


@router.get("/selectable", response_model=List[RaceRoomProfileResponse], summary="List profiles selectable for a tournament")
async def list_selectable(actor: User = Depends(require_api_actor)):
    return await RaceRoomProfileService().list_selectable()


@router.get("/{profile_id}", response_model=RaceRoomProfileResponse, summary="Get a race room profile")
async def get_profile(profile_id: int, actor: User = Depends(require_api_actor)):
    await _load_or_404(profile_id)
    return await RaceRoomProfileService().get_profile(actor, profile_id)


@router.post("", response_model=RaceRoomProfileResponse, status_code=status.HTTP_201_CREATED, summary="Create a race room profile")
async def create_profile(body: RaceRoomProfileCreateRequest, actor: User = Depends(require_write_actor)):
    data = body.model_dump(exclude_unset=True)
    name = data.pop("name")
    return await RaceRoomProfileService().create_profile(actor, name=name, **data)


@router.patch("/{profile_id}", response_model=RaceRoomProfileResponse, summary="Update a race room profile")
async def update_profile(profile_id: int, body: RaceRoomProfileUpdateRequest, actor: User = Depends(require_write_actor)):
    await _load_or_404(profile_id)
    return await RaceRoomProfileService().update_profile(actor, profile_id, **body.model_dump(exclude_unset=True))


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a race room profile")
async def delete_profile(profile_id: int, actor: User = Depends(require_write_actor)):
    await _load_or_404(profile_id)
    await RaceRoomProfileService().delete_profile(actor, profile_id)
