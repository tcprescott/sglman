"""Schemas for the community join-request endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from models import TenantJoinRequest


class JoinRequestResponse(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    status: str
    message: Optional[str] = None
    created_at: datetime
    decided_at: Optional[datetime] = None

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
