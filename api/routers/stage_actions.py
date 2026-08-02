"""Stage write endpoints (Staff or Stream Manager)."""

from fastapi import APIRouter, Depends, status

from api.dependencies import ServiceErrorRoute, require_write_actor
from api.schemas.stage_actions import StageCreateRequest, StageUpdateRequest
from api.schemas.stages import StageResponse
from application.errors import require_found
from application.services import StageService
from application.tenant_context import require_tenant_id
from models import Stage, User

router = APIRouter(prefix="/stages", tags=["Stages"], route_class=ServiceErrorRoute)


async def _load_or_404(stage_id: int) -> Stage:
    return require_found(
        await Stage.get_or_none(id=stage_id, tenant_id=require_tenant_id()),
        "Stage",
    )


@router.post(
    "",
    response_model=StageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a stage",
)
async def create_stage(body: StageCreateRequest, actor: User = Depends(require_write_actor)):
    return await StageService().create_stage(
        name=body.name, stream_url=body.stream_url, is_active=body.is_active, actor=actor,
    )


@router.patch("/{stage_id}", response_model=StageResponse, summary="Update a stage")
async def update_stage(
    stage_id: int, body: StageUpdateRequest, actor: User = Depends(require_write_actor),
):
    stage = await _load_or_404(stage_id)
    await StageService().update_stage(
        stage, name=body.name, stream_url=body.stream_url, is_active=body.is_active, actor=actor,
    )
    return stage


@router.delete(
    "/{stage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a stage",
)
async def delete_stage(stage_id: int, actor: User = Depends(require_write_actor)):
    stage = await _load_or_404(stage_id)
    await StageService().delete_stage(stage, actor=actor)
