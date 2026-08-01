"""In-app feedback endpoints — submit, read your own, and the staff queue.

Gated by the ``FEEDBACK`` feature flag at the router and again inside
``FeedbackService``.

Submitting and reading your own submissions take any token: the web form is
open to every signed-in member, and a person's own feedback is theirs to read
back. The queue (``GET /feedback``) is staff, mirroring the Admin → Feedback
tab. Marking a submission reviewed is re-gated by the service at
``can_view_admin``, which is a wider set than STAFF, so the HTTP layer takes the
coarse write gate and lets the service answer.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status

from api.dependencies import (
    ServiceErrorRoute,
    require_api_actor,
    require_staff,
    require_write_actor,
)
from api.schemas.feedback import (
    FeedbackCreateRequest,
    FeedbackResponse,
    FeedbackReviewRequest,
)
from application.services import FeedbackService
from models import Feedback, User

router = APIRouter(prefix="/feedback", tags=["Feedback"], route_class=ServiceErrorRoute)

MAX_ROWS = 500


def _serialize(row: Feedback, submitter: Optional[User]) -> FeedbackResponse:
    """Serialize one row. The submitter is passed in rather than read off the
    relation: only ``list_recent`` prefetches it, and the other three reads know
    who it is without another query."""
    return FeedbackResponse(
        id=row.id,
        category=getattr(row.category, 'value', row.category),
        status=getattr(row.status, 'value', row.status),
        message=row.message,
        page_url=row.page_url,
        submitted_by_id=row.user_id,
        submitted_by_name=submitter.preferred_name if submitter else None,
        created_at=row.created_at,
    )


@router.get(
    "/mine",
    response_model=List[FeedbackResponse],
    summary="List your own feedback and what happened to it",
)
async def list_mine(
    limit: int = Query(25, ge=1, le=MAX_ROWS, description="Maximum rows to return."),
    actor: User = Depends(require_api_actor),
):
    rows = await FeedbackService().list_mine(actor, limit=limit)
    return [_serialize(row, actor) for row in rows]


@router.get(
    "",
    response_model=List[FeedbackResponse],
    summary="List recent feedback (Staff only)",
)
async def list_feedback(
    limit: int = Query(50, ge=1, le=MAX_ROWS, description="Maximum rows to return."),
    actor: User = Depends(require_staff),
):
    rows = await FeedbackService().list_recent(limit=limit)
    return [_serialize(row, row.user) for row in rows]


@router.post(
    "",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback",
)
async def submit_feedback(
    body: FeedbackCreateRequest, actor: User = Depends(require_write_actor)
):
    row = await FeedbackService().submit(
        actor, body.category, body.message, body.page_url,
    )
    return _serialize(row, actor)


@router.post(
    "/{feedback_id}/reviewed",
    response_model=FeedbackResponse,
    summary="Mark a submission reviewed, or put it back in the queue",
)
async def set_reviewed(
    feedback_id: int,
    body: FeedbackReviewRequest,
    actor: User = Depends(require_write_actor),
):
    row = await FeedbackService().set_reviewed(actor, feedback_id, reviewed=body.reviewed)
    await row.fetch_related('user')
    return _serialize(row, row.user)
