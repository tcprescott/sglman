"""Schemas for player reschedule/cancellation request endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from models import RescheduleRequestKind


class RescheduleRequestResponse(BaseModel):
    id: int
    match_id: int
    kind: str
    status: str
    reason: str
    # UTC, like every other timestamp the REST layer emits. Only Discord gets
    # per-viewer rendering; an API consumer converts for itself.
    proposed_at: Optional[datetime] = None
    original_scheduled_at: Optional[datetime] = None
    opponent_agreed_at: Optional[datetime] = None
    requested_by_id: int
    requested_by_name: Optional[str] = None
    decided_by_id: Optional[int] = None
    decided_by_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    created_at: datetime


class RescheduleRequestCreate(BaseModel):
    kind: RescheduleRequestKind = Field(
        RescheduleRequestKind.RESCHEDULE,
        description="'reschedule' to move the match, 'cancel' to call it off.",
    )
    reason: str = Field(
        ...,
        description="Why the change is needed. Staff decide on this, so it is required.",
    )
    proposed_at: Optional[datetime] = Field(
        None,
        description=(
            "The time you are asking for, in UTC. Omit to say only that you "
            "cannot make the current slot and let staff pick. Ignored for a "
            "'cancel' request, which proposes no time."
        ),
    )


class RescheduleApproveRequest(BaseModel):
    scheduled_at: Optional[datetime] = Field(
        None,
        description=(
            "Approve at a different time than the one proposed, in UTC. Required "
            "when the request named no time. Ignored for a 'cancel' request."
        ),
    )
    note: Optional[str] = Field(
        None, description="Optional message shown to the player with the outcome."
    )


class RescheduleDeclineRequest(BaseModel):
    note: str = Field(
        ...,
        description=(
            "Why the request was refused. Required: a bare 'no' is what this "
            "feature exists to replace."
        ),
    )
