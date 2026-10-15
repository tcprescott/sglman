"""In-app feedback endpoints — submit, read your own, and the staff queue.

Gated by the ``FEEDBACK`` feature flag at the router and again inside
``FeedbackService``.

Submitting and reading your own submissions take any token: the web form is
open to every signed-in member, and a person's own feedback is theirs to read
back. The queue (``GET /feedback``) is staff, mirroring the Admin → Feedback
tab. Marking a submission reviewed is re-gated to STAFF by the service, so the
HTTP layer takes the coarse write gate and lets the service answer.
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
        submitted_by_id=row.user_id,  # type: ignore[attr-defined]
        submitted_by_name=submitter.preferred_name if submitter else None,
        created_at=row.created_at,
    )


@router.get(
    "/mine",
    response_model=List[FeedbackResponse],
    summary="List your own feedback and what happened to it",
    description=(
        "Lists the feedback you've sent, newest first, with each item's status so you can "
        "see whether Staff have reviewed it."
        "\n\n**Who can call this:** Any member; it only ever returns your own feedback."
    ),
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
    description=(
        "Lists the community's feedback queue, newest first, with each submitter's name and "
        "message, whether or not it has been reviewed."
        "\n\n**Who can call this:** Staff."
    ),
)
async def list_feedback(
    limit: int = Query(50, ge=1, le=MAX_ROWS, description="Maximum rows to return."),
    actor: User = Depends(require_staff),
):
    rows = await FeedbackService().list_recent(actor, limit=limit)
    return [_serialize(row, row.user) for row in rows]


@router.post(
    "",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback",
    description=(
        "Sends feedback to the community's Staff and records it in the audit log. It lands in "
        "the queue as `new`.\n\n"
        "Fails with 400 when the message is blank."
        "\n\n**Who can call this:** Any member."
    ),
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
    description=(
        "Sets the submission's status to `reviewed`, or back to `new` when `reviewed` is "
        "false, and records the change in the audit log. The submitter sees the new status "
        "on their own list."
        "\n\n**Who can call this:** Staff."
    ),
)
async def set_reviewed(
    feedback_id: int,
    body: FeedbackReviewRequest,
    actor: User = Depends(require_write_actor),
):
    row = await FeedbackService().set_reviewed(actor, feedback_id, reviewed=body.reviewed)
    await row.fetch_related('user')
    return _serialize(row, row.user)
