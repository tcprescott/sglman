"""Schemas for triforce text endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TriforceSubmitRequest(BaseModel):
    tournament_id: int
    lines: List[str] = Field(..., description="Exactly 3 lines, max 19 chars each")


class TriforceModerateRequest(BaseModel):
    approved: bool = Field(..., description="Approve (true) or reject (false)")


class TriforceTextResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tournament_id: int
    user_id: Optional[int] = None
    text: str
    author: Optional[str] = None
    approved: Optional[bool] = None  # None = pending, True = approved, False = rejected
    approved_at: Optional[datetime] = None
    created_at: datetime
