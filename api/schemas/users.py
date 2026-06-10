"""Schemas for user endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class UserListItem(BaseModel):
    """Lean user representation for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: Optional[str] = None
    discord_id: Optional[int] = None
    pronouns: Optional[str] = None
    is_active: bool


class UserDetailResponse(UserListItem):
    """Full user representation, including held global roles."""

    dm_notifications: bool
    roles: List[str] = []
    created_at: datetime
    updated_at: datetime
