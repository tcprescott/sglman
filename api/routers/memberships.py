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
    description=(
        "Returns the pending requests to join this community, the same queue as the join "
        "requests list on the Users admin page.\n\n"
        "**Who can call this:** Staff."
    ),
)
async def list_pending(actor: User = Depends(require_api_actor)):
    rows = await TenantMembershipService().list_pending_for(actor)
    return [JoinRequestResponse.from_row(r) for r in rows]


@router.post(
    "/{request_id}/approve",
    response_model=JoinRequestResponse,
    summary="Let them in (Staff only)",
    description=(
        "Makes the person a member of this community, lifting any earlier removal, and DMs "
        "them that they're in. Fails with 400 when the request has already been decided.\n\n"
        "**Who can call this:** Staff."
    ),
)
async def approve(request_id: int, actor: User = Depends(require_write_actor)):
    return JoinRequestResponse.from_row(
        await TenantMembershipService().approve_request(actor, request_id)
    )


@router.post(
    "/{request_id}/deny",
    response_model=JoinRequestResponse,
    summary="Decline the request (Staff only)",
    description=(
        "Declines the request and DMs the person that it wasn't approved. They can ask again "
        "after seven days. Fails with 400 when the request has already been decided or the "
        "person is already a member (approve it to clear the request).\n\n"
        "**Who can call this:** Staff."
    ),
)
async def deny(request_id: int, actor: User = Depends(require_write_actor)):
    return JoinRequestResponse.from_row(
        await TenantMembershipService().deny_request(actor, request_id)
    )
