"""Community join-request endpoints: the staff queue and its decisions.

``TenantMembershipService`` gates every call on ``can_grant_roles`` (Staff),
writes the audit rows and DMs the requester either way, mirroring Admin →
Users → join requests.
"""

from typing import List

from fastapi import APIRouter, Depends

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.memberships import JoinRequestResponse
from application.services import TenantMembershipService
from models import User

router = APIRouter(prefix="/join-requests", tags=["Membership"], route_class=ServiceErrorRoute)


@router.get(
    "",
    response_model=List[JoinRequestResponse],
    summary="List requests to join this community that are waiting on a decision (Staff only)",
)
async def list_pending(actor: User = Depends(require_api_actor)):
    rows = await TenantMembershipService().list_pending_for(actor)
    return [JoinRequestResponse.from_row(r) for r in rows]


@router.post(
    "/{request_id}/approve",
    response_model=JoinRequestResponse,
    summary="Let them in (Staff only)",
)
async def approve(request_id: int, actor: User = Depends(require_write_actor)):
    return JoinRequestResponse.from_row(
        await TenantMembershipService().approve_request(actor, request_id)
    )


@router.post(
    "/{request_id}/deny",
    response_model=JoinRequestResponse,
    summary="Decline the request (Staff only)",
)
async def deny(request_id: int, actor: User = Depends(require_write_actor)):
    return JoinRequestResponse.from_row(
        await TenantMembershipService().deny_request(actor, request_id)
    )
