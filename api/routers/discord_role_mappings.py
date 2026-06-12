"""Discord-role-to-app-role mapping endpoints (Staff only).

Reads require a global STAFF role; mutations additionally reject read-only
tokens. ``DiscordRoleMappingService`` re-enforces the Staff check
(``can_grant_roles``) and writes audit logs.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from api.dependencies import ServiceErrorRoute, require_staff, require_write_actor
from api.schemas.discord_role_mappings import (
    DiscordRoleMappingCreate,
    DiscordRoleMappingResponse,
)
from application.services import DiscordRoleMappingService
from models import User

router = APIRouter(
    prefix="/discord-role-mappings",
    tags=["Discord Role Mappings"],
    route_class=ServiceErrorRoute,
)


@router.get(
    "",
    response_model=List[DiscordRoleMappingResponse],
    summary="List Discord role mappings (Staff only)",
)
async def list_mappings(
    guild_id: Optional[int] = Query(None, description="Filter to a single guild."),
    actor: User = Depends(require_staff),
):
    service = DiscordRoleMappingService()
    if guild_id is not None:
        return await service.list_mappings(guild_id)
    return await service.list_all_mappings()


@router.post(
    "",
    response_model=DiscordRoleMappingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Discord role mapping (Staff only)",
)
async def add_mapping(
    body: DiscordRoleMappingCreate, actor: User = Depends(require_write_actor),
):
    return await DiscordRoleMappingService().add_mapping(
        guild_id=body.guild_id,
        discord_role_id=body.discord_role_id,
        discord_role_name=body.discord_role_name,
        app_role=body.app_role,
        actor=actor,
    )


@router.delete(
    "/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Discord role mapping (Staff only)",
)
async def remove_mapping(mapping_id: int, actor: User = Depends(require_write_actor)):
    await DiscordRoleMappingService().remove_mapping(mapping_id, actor=actor)
