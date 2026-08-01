"""Request and response schemas for crew moderation actions."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common import UserBase


class CrewApprovalRequest(BaseModel):
    approved: bool = Field(..., description="Approve (true) or reject (false) the signup")


class CrewSignupInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user: UserBase
    approved: bool
    acknowledged_at: Optional[datetime] = None


class MatchCrewResponse(BaseModel):
    """A match's crew *including* signups nobody has approved yet."""

    match_id: int
    commentators: List[CrewSignupInfo] = Field(default_factory=list)
    trackers: List[CrewSignupInfo] = Field(default_factory=list)
