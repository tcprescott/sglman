"""Player self-service availability endpoints.

Any authenticated user may declare when they are available to play. Unlike
volunteer availability (``/volunteers/me/availability``) there is no opt-in or
role gate. Delegates to :class:`PlayerAvailabilityService`.
"""

from typing import List

from fastapi import APIRouter, Depends, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.player_availability import (
    PlayerAvailabilityResponse,
    SetPlayerAvailabilityRequest,
)
from application.services import PlayerAvailabilityService
from models import User

router = APIRouter(
    prefix="/users/me/availability",
    tags=["Player Availability"],
    route_class=ServiceErrorRoute,
)


@router.get(
    "",
    response_model=List[PlayerAvailabilityResponse],
    summary="List your availability windows",
)
async def list_availability(actor: User = Depends(require_api_actor)):
    return await PlayerAvailabilityService().availability_for(actor)


@router.put(
    "",
    response_model=List[PlayerAvailabilityResponse],
    summary="Replace your availability windows",
)
async def set_availability(
    body: SetPlayerAvailabilityRequest, actor: User = Depends(require_write_actor),
):
    windows = [(w.starts_at, w.ends_at, w.status, w.note) for w in body.windows]
    return await PlayerAvailabilityService().set_windows(actor, windows)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear all your availability windows",
)
async def clear_availability(actor: User = Depends(require_write_actor)):
    await PlayerAvailabilityService().clear(actor)
