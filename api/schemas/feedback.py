"""Schemas for in-app feedback endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from models import FeedbackCategory


class FeedbackResponse(BaseModel):
    id: int
    category: str
    status: str
    message: str
    page_url: Optional[str] = None
    submitted_by_id: Optional[int] = None
    submitted_by_name: Optional[str] = None
    created_at: datetime


class FeedbackCreateRequest(BaseModel):
    message: str
    category: FeedbackCategory = FeedbackCategory.OTHER
    page_url: str = Field(
        default='', max_length=512, description="Where in the app this came from."
    )


class FeedbackReviewRequest(BaseModel):
    reviewed: bool = Field(
        default=True,
        description="True marks it reviewed; false puts it back in the queue.",
    )
