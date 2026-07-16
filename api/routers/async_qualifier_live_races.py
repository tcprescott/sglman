"""Async qualifier live races endpoints.

Author, inspect, open, and cancel synchronous racetime qualifier races. All
authorization is enforced in :class:`AsyncQualifierLiveRaceService` (via
``can_admin_qualifier``); handlers only translate HTTP <-> service calls and do a
tenant-scoped load-or-404 for by-id routes so a missing/cross-tenant race yields
404 (not the service's 400).
"""

from typing import List

from fastapi import APIRouter, Depends, Query, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.async_qualifier_live_races import (
    LiveRaceCreateRequest,
    LiveRaceResponse,
    RunResponse,
)
from application.errors import require_found
from application.services import AsyncQualifierLiveRaceService
from application.tenant_context import require_tenant_id
from models import AsyncQualifierLiveRace, User

router = APIRouter(
    prefix="/async-qualifiers/live-races",
    tags=["Async qualifier live races"],
    route_class=ServiceErrorRoute,
)


async def _load_live_race_or_404(live_race_id: int) -> AsyncQualifierLiveRace:
    return require_found(
        await AsyncQualifierLiveRace.get_or_none(id=live_race_id, tenant_id=require_tenant_id()),
        "Live race",
    )


@router.get("", response_model=List[LiveRaceResponse], summary="List live races for a qualifier")
async def list_live_races(
    qualifier_id: int = Query(..., description="Qualifier to list live races for"),
    actor: User = Depends(require_api_actor),
):
    return await AsyncQualifierLiveRaceService().list_live_races(actor, qualifier_id)


@router.get("/{live_race_id}", response_model=LiveRaceResponse, summary="Get a live race")
async def get_live_race(live_race_id: int, actor: User = Depends(require_api_actor)):
    await _load_live_race_or_404(live_race_id)
    return await AsyncQualifierLiveRaceService().get_live_race(actor, live_race_id)


@router.get(
    "/{live_race_id}/runs",
    response_model=List[RunResponse],
    summary="List captured runs for a live race",
)
async def list_runs(live_race_id: int, actor: User = Depends(require_api_actor)):
    await _load_live_race_or_404(live_race_id)
    return await AsyncQualifierLiveRaceService().list_runs(actor, live_race_id)


@router.post(
    "",
    response_model=LiveRaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a live race",
)
async def create_live_race(payload: LiveRaceCreateRequest, actor: User = Depends(require_write_actor)):
    return await AsyncQualifierLiveRaceService().create_live_race(
        actor,
        payload.pool_id,
        match_title=payload.match_title,
        permalink_id=payload.permalink_id,
        episode_id=payload.episode_id,
    )


@router.post(
    "/{live_race_id}/open-room",
    response_model=LiveRaceResponse,
    summary="Open a racetime room for the live race",
)
async def open_room(live_race_id: int, actor: User = Depends(require_write_actor)):
    await _load_live_race_or_404(live_race_id)
    return await AsyncQualifierLiveRaceService().open_room(actor, live_race_id)


@router.delete(
    "/{live_race_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a live race",
)
async def cancel_live_race(live_race_id: int, actor: User = Depends(require_write_actor)):
    await _load_live_race_or_404(live_race_id)
    await AsyncQualifierLiveRaceService().cancel_live_race(actor, live_race_id)
