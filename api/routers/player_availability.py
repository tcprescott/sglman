"""Player availability endpoints.

Any authenticated user may declare when they are available to play. Unlike
volunteer availability (``/volunteers/me/availability``) there is no opt-in or
role gate. Delegates to :class:`PlayerAvailabilityService`.

Reading *another* player's windows is staff, matching ``GET /users/{id}`` and
the MCP ``get_player_availability`` tool — schedulers need the whole field's
answers, and a player's own windows stay self-service. It lives on a second
router so ``/users/me/availability`` is matched before ``/users/{id}/…``.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from api._helpers import load_community_user_or_404
from api.dependencies import (
    ServiceErrorRoute,
    require_api_actor,
    require_write_actor,
)
from api.schemas.player_availability import (
    PlayerAvailabilityResponse,
    SetPlayerAvailabilityRequest,
)
from application.services import AuthService, PlayerAvailabilityService
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


other_players_router = APIRouter(
    prefix="/users",
    tags=["Player Availability"],
    route_class=ServiceErrorRoute,
)


@other_players_router.get(
    "/{user_id}/availability",
    response_model=List[PlayerAvailabilityResponse],
    summary="List another player's availability windows (self or Staff)",
)
async def list_availability_for(
    user_id: int,
    start: Optional[datetime] = Query(
        None, description="Only windows overlapping at or after this time (UTC ISO 8601)."
    ),
    end: Optional[datetime] = Query(
        None, description="Only windows overlapping at or before this time (UTC ISO 8601)."
    ),
    actor: User = Depends(require_api_actor),
):
    if user_id != actor.id:
        await AuthService.ensure(
            await AuthService.is_staff(actor),
            "Staff access required to view other players' availability",
        )
    target = await load_community_user_or_404(user_id, actor)
    windows = await PlayerAvailabilityService().availability_for(target)
    return [
        window for window in windows
        if (start is None or window.ends_at >= start)
        and (end is None or window.starts_at <= end)
    ]
