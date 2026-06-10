"""Request schemas for crew moderation actions."""

from pydantic import BaseModel, Field


class CrewApprovalRequest(BaseModel):
    approved: bool = Field(..., description="Approve (true) or reject (false) the signup")
