"""Preset endpoints — tenant-authored seed-rolling presets.

Reads are open to any authenticated token (the management gate lives in the
service). Writes reject read-only tokens at the HTTP layer and are re-gated by
``PresetService`` (``can_manage_presets``: STAFF / SUPER_ADMIN / PRESET_MANAGER).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.presets import (
    PresetCreateRequest,
    PresetResponse,
    PresetUpdateRequest,
)
from application.services import PresetService
from models import User

router = APIRouter(prefix="/presets", tags=["Presets"], route_class=ServiceErrorRoute)


@router.get("", response_model=List[PresetResponse], summary="List presets")
async def list_presets(
    randomizer: Optional[str] = Query(None, description="Filter to one randomizer (read-only, ungated)"),
    actor: User = Depends(require_api_actor),
):
    service = PresetService()
    if randomizer is not None:
        return await service.list_by_randomizer(randomizer)
    return await service.list_presets(actor)


@router.get("/selectable", response_model=List[PresetResponse], summary="List selectable presets")
async def list_selectable(actor: User = Depends(require_api_actor)):
    return await PresetService().list_selectable()


@router.get("/{preset_id}", response_model=PresetResponse, summary="Get a preset")
async def get_preset(preset_id: int, actor: User = Depends(require_api_actor)):
    return await PresetService().get_preset(actor, preset_id)


@router.post("", response_model=PresetResponse, status_code=status.HTTP_201_CREATED, summary="Create a preset")
async def create_preset(body: PresetCreateRequest, actor: User = Depends(require_write_actor)):
    return await PresetService().create_preset(
        actor,
        name=body.name,
        randomizer=body.randomizer,
        settings=body.settings,
        description=body.description,
    )


@router.patch("/{preset_id}", response_model=PresetResponse, summary="Update a preset")
async def update_preset(preset_id: int, body: PresetUpdateRequest, actor: User = Depends(require_write_actor)):
    return await PresetService().update_preset(
        actor, preset_id, **body.model_dump(exclude_unset=True)
    )


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a preset")
async def delete_preset(preset_id: int, actor: User = Depends(require_write_actor)):
    await PresetService().delete_preset(actor, preset_id)


@router.post("/import-builtins", response_model=List[PresetResponse], summary="Import built-in presets")
async def import_builtins(actor: User = Depends(require_write_actor)):
    return await PresetService().import_builtins(actor)
