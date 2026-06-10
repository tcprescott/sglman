"""Triforce text endpoints (read)."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.triforce import (
    TriforceModerateRequest,
    TriforceSubmitRequest,
    TriforceTextResponse,
)
from application.services import TriforceTextService
from application.services.auth_service import AuthService
from models import User

router = APIRouter(prefix="/triforce-texts", tags=["Triforce Texts"], route_class=ServiceErrorRoute)


@router.get(
    "/mine",
    response_model=List[TriforceTextResponse],
    summary="List your own triforce text submissions for a tournament",
)
async def list_my_submissions(
    tournament_id: int = Query(..., description="Tournament to list your submissions for"),
    actor: User = Depends(require_api_actor),
):
    return await TriforceTextService().list_user_submissions(tournament_id, actor)


@router.get(
    "",
    response_model=List[TriforceTextResponse],
    summary="List submissions for moderation",
    description="Requires Staff or Tournament Admin of the given tournament.",
)
async def list_for_moderation(
    tournament_id: int = Query(..., description="Tournament to moderate"),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter: pending, approved, or rejected"
    ),
    actor: User = Depends(require_api_actor),
):
    is_moderator = await AuthService.is_staff(actor) or await AuthService.is_tournament_admin(
        actor, tournament_id
    )
    if not is_moderator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to moderate this pool",
        )
    return await TriforceTextService().list_for_moderation(tournament_id, status=status_filter)


# --- Writes -----------------------------------------------------------------


@router.post(
    "",
    response_model=TriforceTextResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a triforce text",
)
async def submit_text(body: TriforceSubmitRequest, actor: User = Depends(require_write_actor)):
    return await TriforceTextService().submit(body.tournament_id, body.lines, actor)


@router.post(
    "/{text_id}/moderate",
    response_model=TriforceTextResponse,
    summary="Approve or reject a submission (Staff or Tournament Admin)",
)
async def moderate_text(
    text_id: int, body: TriforceModerateRequest, actor: User = Depends(require_write_actor),
):
    return await TriforceTextService().moderate(text_id, body.approved, actor)


@router.delete(
    "/{text_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a submission (Staff or Tournament Admin)",
)
async def delete_text(text_id: int, actor: User = Depends(require_write_actor)):
    await TriforceTextService().delete(text_id, actor)
