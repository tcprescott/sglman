"""Player reschedule/cancellation request endpoints.

Every route delegates to ``MatchRescheduleService``, which enforces who may ask
and who may decide, writes the audit rows, and queues the Discord notifications.

The permission split mirrors the web surface exactly. Raising, withdrawing and
agreeing take any write token, because the service checks that the actor plays
in the match. Deciding is re-gated inside the service on ``can_crud_match`` —
staff or the tournament's admin — which is wider than global STAFF, so the HTTP
layer takes the coarse write gate and lets the service answer.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from api.dependencies import ServiceErrorRoute, require_api_actor, require_write_actor
from api.schemas.reschedule_requests import (
    RescheduleApproveRequest,
    RescheduleDeclineRequest,
    RescheduleRequestCreate,
    RescheduleRequestResponse,
)
from application.services import MatchRescheduleService
from models import MatchRescheduleRequest, User

router = APIRouter(tags=["Reschedule requests"], route_class=ServiceErrorRoute)

MAX_ROWS = 500


def _serialize(row: MatchRescheduleRequest) -> RescheduleRequestResponse:
    decider = row.decided_by
    return RescheduleRequestResponse(
        id=row.id,
        match_id=row.match_id,  # type: ignore[attr-defined]
        kind=getattr(row.kind, 'value', row.kind),
        status=getattr(row.status, 'value', row.status),
        reason=row.reason,
        proposed_at=row.proposed_at,
        original_scheduled_at=row.original_scheduled_at,
        opponent_agreed_at=row.opponent_agreed_at,
        requested_by_id=row.requested_by_id,  # type: ignore[attr-defined]
        requested_by_name=row.requested_by.preferred_name if row.requested_by else None,
        decided_by_id=row.decided_by_id,  # type: ignore[attr-defined]
        decided_by_name=decider.preferred_name if decider else None,
        decided_at=row.decided_at,
        decision_note=row.decision_note,
        created_at=row.created_at,
    )


async def _reload(service: MatchRescheduleService, request_id: int, fallback):
    """Re-read a decided request so the response carries its prefetched relations.

    Falls back to the in-memory row for an approved cancellation, whose match —
    and with it the request — is deleted by the time this runs.
    """
    row = await service.get_by_id(request_id)
    return _serialize(row) if row is not None else _serialize(fallback)


@router.get(
    "/reschedule-requests/mine",
    response_model=List[RescheduleRequestResponse],
    summary="List your own reschedule requests and what happened to them",
)
async def list_mine(
    limit: int = Query(25, ge=1, le=MAX_ROWS, description="Maximum rows to return."),
    actor: User = Depends(require_api_actor),
):
    rows = await MatchRescheduleService().list_mine(actor, limit=limit)
    return [_serialize(row) for row in rows]


@router.get(
    "/reschedule-requests",
    response_model=List[RescheduleRequestResponse],
    summary="List reschedule requests waiting on a decision (admin)",
)
async def list_pending(actor: User = Depends(require_api_actor)):
    """The staff queue. Gated in the service on `can_view_admin` — a request
    carries the player's own words about why they need the change, which is not
    schedule data and is nobody else's to read."""
    rows = await MatchRescheduleService().list_pending(actor)
    return [_serialize(row) for row in rows]


@router.post(
    "/matches/{match_id}/reschedule-requests",
    response_model=RescheduleRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ask staff to move or call off a match you are playing in",
)
async def submit_request(
    match_id: int,
    body: RescheduleRequestCreate,
    actor: User = Depends(require_write_actor),
):
    service = MatchRescheduleService()
    request = await service.submit(
        match_id, actor,
        kind=body.kind, reason=body.reason, proposed_at=body.proposed_at,
    )
    return await _reload(service, request.id, request)


@router.get(
    "/matches/{match_id}/reschedule-requests",
    response_model=List[RescheduleRequestResponse],
    summary="List the reschedule requests raised against a match",
)
async def list_for_match(match_id: int, actor: User = Depends(require_api_actor)):
    """Whoever could decide these, or a player in the match reading their own."""
    rows = await MatchRescheduleService().list_for_match(match_id, actor)
    return [_serialize(row) for row in rows]


@router.post(
    "/reschedule-requests/{request_id}/agree",
    response_model=RescheduleRequestResponse,
    summary="Agree with your opponent's request (advisory; staff still decide)",
)
async def agree(request_id: int, actor: User = Depends(require_write_actor)):
    service = MatchRescheduleService()
    request = await service.record_opponent_agreement(request_id, actor)
    return await _reload(service, request_id, request)


@router.post(
    "/reschedule-requests/{request_id}/withdraw",
    response_model=RescheduleRequestResponse,
    summary="Take back a request you raised",
)
async def withdraw(request_id: int, actor: User = Depends(require_write_actor)):
    service = MatchRescheduleService()
    request = await service.withdraw(request_id, actor)
    return await _reload(service, request_id, request)


@router.post(
    "/reschedule-requests/{request_id}/approve",
    response_model=RescheduleRequestResponse,
    summary="Approve a request, performing the reschedule or cancellation",
)
async def approve(
    request_id: int,
    body: Optional[RescheduleApproveRequest] = None,
    actor: User = Depends(require_write_actor),
):
    service = MatchRescheduleService()
    body = body or RescheduleApproveRequest(scheduled_at=None, note=None)
    request = await service.approve(
        request_id, actor, scheduled_at=body.scheduled_at, note=body.note,
    )
    return await _reload(service, request_id, request)


@router.post(
    "/reschedule-requests/{request_id}/decline",
    response_model=RescheduleRequestResponse,
    summary="Decline a request, in your own words",
)
async def decline(
    request_id: int,
    body: RescheduleDeclineRequest,
    actor: User = Depends(require_write_actor),
):
    service = MatchRescheduleService()
    request = await service.decline(request_id, actor, body.note)
    return await _reload(service, request_id, request)
