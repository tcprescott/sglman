"""Seed-generation endpoints.

Exposes the list of supported randomizers and a single roll-a-seed action over
the existing :class:`SeedGenerationService`. Seed generation itself is ungated
(any authenticated token may roll); the HTTP dependency is the only authz layer.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.seeds import RandomizerResponse, SeedGenerateRequest, SeedResponse
from application.errors import require_found
from application.services import FeatureFlagService, SeedGenerationService
from application.tenant_context import require_tenant_id
from models import Preset, User

router = APIRouter(prefix="/seeds", tags=["Seeds"], route_class=ServiceErrorRoute)


@router.get(
    "/randomizers",
    response_model=List[RandomizerResponse],
    summary="List supported randomizers",
)
async def list_randomizers(actor: User = Depends(require_api_actor)):
    # Filter flag-gated randomizers the tenant is not authorized for, mirroring
    # the web selector surfaces (a stored preset stays valid, but the catalogue
    # advertises only what this community may actually roll).
    live = await FeatureFlagService().enabled_flags()
    return [
        RandomizerResponse(
            randomizer=r,
            supports_triforce_texts=SeedGenerationService.supports_triforce_texts(r),
        )
        for r in SeedGenerationService.available_randomizers(live)
    ]


@router.post("", response_model=SeedResponse, summary="Generate a seed")
async def generate_seed(body: SeedGenerateRequest, actor: User = Depends(require_write_actor)):
    # Roll-boundary gate for a flag-gated randomizer (keyed upstream): hide it as
    # a 404, the REST mirror of the web feature gate, so the API can't reach a
    # randomizer the community isn't authorized for.
    gate_flag = SeedGenerationService.gating_flag(body.randomizer)
    if gate_flag is not None and not await FeatureFlagService().is_enabled(gate_flag):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This feature is not enabled for this community.",
        )
    preset = None
    if body.preset_id is not None:
        preset = require_found(
            await Preset.get_or_none(id=body.preset_id, tenant_id=require_tenant_id()), "Preset"
        )
    url = await SeedGenerationService().generate_seed(body.randomizer, preset)
    return SeedResponse(url=url)
