"""System configuration endpoints (Staff only)."""

from typing import List

from fastapi import APIRouter, Depends

from api.dependencies import ServiceErrorRoute, require_staff, require_staff_write
from api.schemas.config import ConfigEntryResponse, ConfigValueUpdate
from application.errors import require_found
from application.services import SystemConfigService
from application.tenant_context import require_tenant_id
from models import SystemConfiguration, User

router = APIRouter(prefix="/config", tags=["System Config"], route_class=ServiceErrorRoute)


@router.get(
    "",
    response_model=List[ConfigEntryResponse],
    summary="List all configuration entries",
)
async def list_config(actor: User = Depends(require_staff)):
    # Scope to the token's tenant; SystemConfiguration.name is unique per tenant.
    return await SystemConfiguration.filter(tenant_id=require_tenant_id()).order_by('name')


@router.get(
    "/{key}",
    response_model=ConfigEntryResponse,
    summary="Get a configuration entry",
)
async def get_config(key: str, actor: User = Depends(require_staff)):
    return require_found(
        await SystemConfiguration.get_or_none(name=key, tenant_id=require_tenant_id()),
        "Config key",
    )


@router.put(
    "/{key}",
    response_model=ConfigEntryResponse,
    summary="Set a configuration entry (Staff only)",
)
async def set_config(key: str, body: ConfigValueUpdate, actor: User = Depends(require_staff_write)):
    return await SystemConfigService.set_raw(key, body.value, actor)
