"""System configuration endpoints (Staff only)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import ServiceErrorRoute, require_staff, require_write_actor
from api.schemas.config import ConfigEntryResponse, ConfigValueUpdate
from application.services import SystemConfigService
from models import SystemConfiguration, User

router = APIRouter(prefix="/config", tags=["System Config"], route_class=ServiceErrorRoute)


@router.get(
    "",
    response_model=List[ConfigEntryResponse],
    summary="List all configuration entries",
)
async def list_config(actor: User = Depends(require_staff)):
    return await SystemConfiguration.all().order_by('name')


@router.get(
    "/{key}",
    response_model=ConfigEntryResponse,
    summary="Get a configuration entry",
)
async def get_config(key: str, actor: User = Depends(require_staff)):
    entry = await SystemConfiguration.get_or_none(name=key)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config key not found")
    return entry


@router.put(
    "/{key}",
    response_model=ConfigEntryResponse,
    summary="Set a configuration entry (Staff only)",
)
async def set_config(key: str, body: ConfigValueUpdate, actor: User = Depends(require_write_actor)):
    return await SystemConfigService.set_raw(key, body.value, actor)
