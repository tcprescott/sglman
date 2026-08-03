"""Seed-generation endpoints.

Exposes the list of supported randomizers and a single roll-a-seed action over
the existing :class:`SeedGenerationService`. Seed generation itself is ungated
(any authenticated token may roll); the HTTP dependency is the only authz layer.
"""

from typing import List

from fastapi import APIRouter, Depends, Response, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.seeds import (
    RandomizerResponse,
    SeedGenerateRequest,
    SeedResponse,
    SeedTaskResponse,
)
from application.errors import require_found
from application.services import (
    ProviderTaskService,
    RandomizerCredentialService,
    SeedGenerationService,
    SeedRollService,
)
from application.tenant_context import require_tenant_id
from models import Preset, ProviderTask, User

router = APIRouter(prefix="/seeds", tags=["Seeds"], route_class=ServiceErrorRoute)


@router.get(
    "/randomizers",
    response_model=List[RandomizerResponse],
    summary="List supported randomizers",
)
async def list_randomizers(actor: User = Depends(require_api_actor)):
    # Drop randomizers whose upstream needs a key this community has not supplied,
    # mirroring the web selector surfaces (a stored preset stays valid, but the
    # catalogue advertises only what this community may actually roll).
    configured = await RandomizerCredentialService().configured_randomizers()
    return [
        RandomizerResponse(
            randomizer=r,
            supports_triforce_texts=SeedGenerationService.supports_triforce_texts(r),
        )
        for r in SeedGenerationService.available_randomizers(configured)
    ]


@router.post("", summary="Generate a seed")
async def generate_seed(
    body: SeedGenerateRequest, response: Response,
    actor: User = Depends(require_write_actor),
):
    """Roll a seed.

    **200** with the permalink for a synchronous randomizer. **202** with a task
    id for one whose upstream is a queue (`dk64r`), because those take minutes
    and there is no url to hand back yet — poll `GET /seeds/tasks/{id}`.
    """
    # A keyed randomizer this community has not configured raises inside the
    # generator; ServiceErrorRoute turns that ValueError into a 400 naming the
    # missing credential.
    preset = None
    if body.preset_id is not None:
        preset = require_found(
            await Preset.get_or_none(id=body.preset_id, tenant_id=require_tenant_id()), "Preset"
        )

    if body.randomizer in SeedGenerationService.ASYNC_RANDOMIZERS:
        task = await ProviderTaskService().queue(
            provider=body.randomizer, operation='generate_seed', actor=actor,
            preset_id=preset.id if preset is not None else None,
        )
        task = await SeedRollService().submit(task, preset)
        response.status_code = status.HTTP_202_ACCEPTED
        return _task_response(task)

    url = await SeedGenerationService().generate_seed(body.randomizer, preset)
    return SeedResponse(url=url)


@router.get(
    "/tasks/{task_id}",
    response_model=SeedTaskResponse,
    summary="Check an asynchronous seed roll",
)
async def get_seed_task(task_id: int, actor: User = Depends(require_api_actor)):
    """Where a queued roll has got to. 404 for a task another community owns."""
    task = require_found(await ProviderTaskService().get_by_id(task_id), "Task")
    return _task_response(task)


def _task_response(task: ProviderTask) -> SeedTaskResponse:
    # The permalink lives on the GeneratedSeeds row the completion wrote, not on
    # the task, so a finished task is resolved through its match. A task rolled
    # without a match (a bare API roll) has nowhere to put one, and reports
    # succeeded with no url.
    seed = getattr(getattr(task, 'match', None), 'generated_seed', None)
    return SeedTaskResponse(
        task_id=task.id,
        randomizer=task.provider,
        status=task.status.value if hasattr(task.status, 'value') else str(task.status),
        url=seed.seed_url if seed is not None else None,
        error=task.error,
    )
