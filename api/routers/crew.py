"""Crew moderation endpoints (approval and acknowledgment).

``crew_type`` is ``commentator`` or ``tracker``; ``crew_id`` is the id of the
Commentator/Tracker signup row.
"""

from fastapi import APIRouter, Depends

from api.dependencies import ServiceErrorRoute, require_write_actor
from api.schemas.crew import CrewApprovalRequest
from application.errors import require_found
from application.services import CrewService
from models import User

router = APIRouter(prefix="/crew", tags=["Crew"], route_class=ServiceErrorRoute)


@router.post(
    "/{crew_type}/{crew_id}/approval",
    summary="Approve or reject a crew signup",
    description="Requires Staff, Tournament Admin, or Crew Coordinator of the match's tournament.",
)
async def update_crew_approval(
    crew_type: str,
    crew_id: int,
    body: CrewApprovalRequest,
    actor: User = Depends(require_write_actor),
):
    service = CrewService()
    crew_member = require_found(
        await service.get_crew_member_by_id(crew_id, crew_type), "Crew signup"
    )
    await service.update_crew_approval(crew_member, crew_type, body.approved, actor=actor)
    return {"detail": "approved" if body.approved else "rejected"}


@router.post(
    "/{crew_type}/{crew_id}/acknowledge",
    summary="Acknowledge your own (approved) crew assignment",
)
async def acknowledge_crew_assignment(
    crew_type: str,
    crew_id: int,
    actor: User = Depends(require_write_actor),
):
    await CrewService().acknowledge_crew_assignment(crew_id, crew_type, actor)
    return {"detail": "acknowledged"}
