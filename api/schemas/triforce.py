"""Schemas for triforce text endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TriforceSubmitRequest(BaseModel):
    tournament_id: int = Field(..., description="Tournament whose pool the text goes into.")
    lines: List[str] = Field(
        ...,
        description=(
            "Exactly 3 lines of at most 19 characters each: letters, digits, spaces, common "
            "punctuation, arrows, hiragana and katakana. At least one line must have text."
        ),
    )


class TriforceModerateRequest(BaseModel):
    approved: bool = Field(..., description="Approve (true) or reject (false).")


class TriforceTextResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Submission ID.")
    tournament_id: int = Field(..., description="Tournament whose pool it belongs to.")
    user_id: Optional[int] = Field(
        None, description="User ID of the submitter; null if their account has been deleted."
    )
    text: str = Field(..., description="The three lines joined with newlines.")
    author: Optional[str] = Field(
        None, description="The submitter's display name when they submitted it."
    )
    approved: Optional[bool] = Field(
        None, description="Moderation state: null is pending, true approved, false rejected."
    )
    approved_at: Optional[datetime] = Field(
        None, description="When it was approved or rejected (UTC); null while pending."
    )
    created_at: datetime = Field(..., description="When it was submitted (UTC).")
