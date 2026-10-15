"""Schemas for in-app feedback endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from models import FeedbackCategory


class FeedbackResponse(BaseModel):
    id: int = Field(..., description="Feedback ID.")
    category: str = Field(
        ..., description="Category: `bug`, `suggestion`, `praise` or `other`."
    )
    status: str = Field(
        ..., description="Review status: `new` (still in the queue) or `reviewed`."
    )
    message: str = Field(..., description="What the submitter wrote.")
    page_url: Optional[str] = Field(
        None, description="Where in the app it was sent from; may be empty."
    )
    submitted_by_id: Optional[int] = Field(None, description="User ID of the submitter.")
    submitted_by_name: Optional[str] = Field(None, description="Display name of the submitter.")
    created_at: datetime = Field(..., description="When it was submitted (UTC).")


class FeedbackCreateRequest(BaseModel):
    message: str = Field(..., description="What you want to tell Staff. Must not be blank.")
    category: FeedbackCategory = Field(
        FeedbackCategory.OTHER,
        description="Category: `bug`, `suggestion`, `praise` or `other` (the default).",
    )
    page_url: str = Field(
        default='', max_length=512, description="Where in the app this came from."
    )


class FeedbackReviewRequest(BaseModel):
    reviewed: bool = Field(
        default=True,
        description="True marks it reviewed; false puts it back in the queue.",
    )
