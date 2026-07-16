"""SpeedGaming sync endpoints — tenant event links, staging episodes, on-demand sync.

All routes delegate to :class:`SpeedGamingSyncService`, which gates every method
on ``AuthService.can_manage_sync`` (STAFF / super-admin / ``SYNC_ADMIN``). The
HTTP dep only distinguishes read (any token) from write (rejects read-only
tokens); authorization proper is enforced in-service.
"""

from typing import List

from fastapi import APIRouter, Depends, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.speedgaming import (
    SpeedGamingEpisodeResponse,
    SpeedGamingLinkCreateRequest,
    SpeedGamingLinkResponse,
    SpeedGamingLinkUpdateRequest,
    SyncResultResponse,
)
from application.errors import require_found
from application.services import SpeedGamingSyncService
from application.tenant_context import require_tenant_id
from models import SpeedGamingEventLink, User

router = APIRouter(prefix="/speedgaming", tags=["SpeedGaming"], route_class=ServiceErrorRoute)


async def _load_link_or_404(link_id: int) -> SpeedGamingEventLink:
    return require_found(
        await SpeedGamingEventLink.get_or_none(id=link_id, tenant_id=require_tenant_id()),
        "SpeedGaming event link",
    )


# --- Links ----------------------------------------------------------------

@router.get("/links", response_model=List[SpeedGamingLinkResponse], summary="List SpeedGaming event links")
async def list_links(actor: User = Depends(require_api_actor)):
    return await SpeedGamingSyncService().list_links(actor)


@router.get(
    "/links/{link_id}/episodes",
    response_model=List[SpeedGamingEpisodeResponse],
    summary="List staged episodes for a link",
)
async def list_episodes(link_id: int, actor: User = Depends(require_api_actor)):
    await _load_link_or_404(link_id)
    return await SpeedGamingSyncService().list_episodes(actor, link_id)


@router.post(
    "/links",
    response_model=SpeedGamingLinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a SpeedGaming event link",
)
async def create_link(body: SpeedGamingLinkCreateRequest, actor: User = Depends(require_write_actor)):
    return await SpeedGamingSyncService().create_link(actor, **body.model_dump())


@router.patch("/links/{link_id}", response_model=SpeedGamingLinkResponse, summary="Update a SpeedGaming event link")
async def update_link(
    link_id: int,
    body: SpeedGamingLinkUpdateRequest,
    actor: User = Depends(require_write_actor),
):
    return await SpeedGamingSyncService().update_link(actor, link_id, **body.model_dump(exclude_unset=True))


@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a SpeedGaming event link")
async def delete_link(link_id: int, actor: User = Depends(require_write_actor)):
    await SpeedGamingSyncService().delete_link(actor, link_id)


@router.post("/links/{link_id}/sync", response_model=SyncResultResponse, summary="Run an on-demand sync for a link")
async def sync_link(link_id: int, actor: User = Depends(require_write_actor)):
    result = await SpeedGamingSyncService().sync_now(actor, link_id)
    return result.as_dict()
