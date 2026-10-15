"""Schemas for the community join-request endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from models import TenantJoinRequest


class JoinRequestResponse(BaseModel):
    id: int = Field(..., description="The join request's ID.")
    user_id: int = Field(..., description="ID of the person asking to join.")
    user_name: Optional[str] = Field(None, description="Their display name, or their username when they have none.")
    status: str = Field(..., description="Where the request stands. One of: pending, approved, denied.")
    message: Optional[str] = Field(None, description="The note the person wrote when asking to join, if any.")
    created_at: datetime = Field(..., description="When the request was made (UTC).")
    decided_at: Optional[datetime] = Field(None, description="When staff approved or declined it (UTC). Null while pending.")

    @classmethod
    def from_row(cls, request: TenantJoinRequest) -> 'JoinRequestResponse':
        """``user`` must be loaded."""
        return cls(
            id=request.id,
            user_id=request.user_id,
            user_name=request.user.preferred_name,
            status=getattr(request.status, 'value', request.status),
            message=request.message,
            created_at=request.created_at,
            decided_at=request.decided_at,
        )
