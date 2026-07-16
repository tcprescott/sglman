"""Racetime bot endpoints — global / platform (super-admin) administration.

A :class:`~models.RacetimeBot` is **global** (no ``tenant`` FK). Reads require
the global ``SUPER_ADMIN`` role; mutations additionally reject read-only tokens.
Responses are always built from ``RacetimeBotService.serialize(bot)`` so the
privileged ``client_secret`` is never serialized.
"""

from typing import List

from fastapi import APIRouter, Depends, status

from api.dependencies import (
    ServiceErrorRoute,
    require_super_admin,
    require_super_admin_write,
)
from api.schemas.racetime_bots import (
    RacetimeBotCreateRequest,
    RacetimeBotGrantRequest,
    RacetimeBotGrantResponse,
    RacetimeBotResponse,
    RacetimeBotUpdateRequest,
)
from application.errors import require_found
from application.services import RacetimeBotService
from models import RacetimeBot, User

router = APIRouter(prefix="/racetime-bots", tags=["Racetime bots"], route_class=ServiceErrorRoute)


async def _load_bot_or_404(bot_id: int) -> RacetimeBot:
    """Global load-or-404 (no tenant filter) for a documented 404 on missing ids."""
    return require_found(await RacetimeBot.get_or_none(id=bot_id), "Racetime bot")


# --- Bot CRUD -------------------------------------------------------------

@router.get("", response_model=List[RacetimeBotResponse], summary="List racetime bots")
async def list_bots(actor: User = Depends(require_super_admin)):
    service = RacetimeBotService()
    bots = await service.list_bots(actor)
    return [service.serialize(b) for b in bots]


@router.get("/active", response_model=List[RacetimeBotResponse], summary="List active racetime bots")
async def list_active_bots(actor: User = Depends(require_super_admin)):
    service = RacetimeBotService()
    bots = await service.list_active_bots()
    return [service.serialize(b) for b in bots]


@router.get("/{bot_id}", response_model=RacetimeBotResponse, summary="Get a racetime bot")
async def get_bot(bot_id: int, actor: User = Depends(require_super_admin)):
    await _load_bot_or_404(bot_id)
    service = RacetimeBotService()
    return service.serialize(await service.get_bot(actor, bot_id))


@router.post("", response_model=RacetimeBotResponse, status_code=status.HTTP_201_CREATED, summary="Create a racetime bot")
async def create_bot(payload: RacetimeBotCreateRequest, actor: User = Depends(require_super_admin_write)):
    service = RacetimeBotService()
    bot = await service.create_bot(actor, **payload.model_dump())
    return service.serialize(bot)


@router.patch("/{bot_id}", response_model=RacetimeBotResponse, summary="Update a racetime bot")
async def update_bot(bot_id: int, payload: RacetimeBotUpdateRequest, actor: User = Depends(require_super_admin_write)):
    await _load_bot_or_404(bot_id)
    service = RacetimeBotService()
    bot = await service.update_bot(actor, bot_id, **payload.model_dump(exclude_unset=True))
    return service.serialize(bot)


@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a racetime bot")
async def delete_bot(bot_id: int, actor: User = Depends(require_super_admin_write)):
    await _load_bot_or_404(bot_id)
    await RacetimeBotService().delete_bot(actor, bot_id)


# --- Tenant authorization grants ------------------------------------------

@router.get("/{bot_id}/grants", response_model=List[RacetimeBotGrantResponse], summary="List tenant grants for a bot")
async def list_grants(bot_id: int, actor: User = Depends(require_super_admin)):
    await _load_bot_or_404(bot_id)
    return await RacetimeBotService().list_grants(actor, bot_id)


@router.post("/{bot_id}/grants", response_model=RacetimeBotGrantResponse, status_code=status.HTTP_201_CREATED, summary="Grant a tenant access to a bot")
async def grant_tenant(bot_id: int, payload: RacetimeBotGrantRequest, actor: User = Depends(require_super_admin_write)):
    await _load_bot_or_404(bot_id)
    return await RacetimeBotService().grant_tenant(actor, bot_id, payload.tenant_id)


@router.delete("/{bot_id}/grants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke a tenant's access to a bot")
async def revoke_tenant(bot_id: int, tenant_id: int, actor: User = Depends(require_super_admin_write)):
    await _load_bot_or_404(bot_id)
    await RacetimeBotService().revoke_tenant(actor, bot_id, tenant_id)
