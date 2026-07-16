"""Seed-generation endpoints.

Exposes the list of supported randomizers and a single roll-a-seed action over
the existing :class:`SeedGenerationService`. Seed generation itself is ungated
(any authenticated token may roll); the HTTP dependency is the only authz layer.
"""

from typing import List

from fastapi import APIRouter, Depends

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.seeds import RandomizerResponse, SeedGenerateRequest, SeedResponse
from application.errors import require_found
from application.services import SeedGenerationService
from application.tenant_context import require_tenant_id
from models import Preset, User

router = APIRouter(prefix="/seeds", tags=["Seeds"], route_class=ServiceErrorRoute)


@router.get(
    "/randomizers",
    response_model=List[RandomizerResponse],
    summary="List supported randomizers",
)
async def list_randomizers(actor: User = Depends(require_api_actor)):
    return [
        RandomizerResponse(
            randomizer=r,
            supports_triforce_texts=SeedGenerationService.supports_triforce_texts(r),
        )
        for r in SeedGenerationService.AVAILABLE_RANDOMIZERS
    ]


@router.post("", response_model=SeedResponse, summary="Generate a seed")
async def generate_seed(body: SeedGenerateRequest, actor: User = Depends(require_write_actor)):
    preset = None
    if body.preset_id is not None:
        preset = require_found(
            await Preset.get_or_none(id=body.preset_id, tenant_id=require_tenant_id()), "Preset"
        )
    url = await SeedGenerationService().generate_seed(body.randomizer, preset)
    return SeedResponse(url=url)
