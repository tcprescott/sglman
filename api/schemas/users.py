"""Schemas for user endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserListItem(BaseModel):
    """Lean user representation for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="The user's ID. Accounts are shared across communities, so it is the same everywhere.")
    username: str = Field(..., description="The account's username.")
    display_name: Optional[str] = Field(None, description="The name the person chose to be shown by, if any.")
    discord_id: Optional[int] = Field(None, description="The linked Discord user ID, or null for an account without one.")
    pronouns: Optional[str] = Field(None, description="The person's pronouns, if they gave any.")
    is_active: bool = Field(
        ..., description="False when the account is deactivated, which locks it out of every community.",
    )


class UserDetailResponse(UserListItem):
    """Full user representation, including the roles held in this community."""

    dm_notifications: bool = Field(..., description="Whether the person gets notifications as Discord DMs.")
    roles: List[str] = Field(
        [],
        description=(
            "Roles the person holds in this community, sorted. Values are from: staff, proctor, stream_manager, triforce_submitter, volunteer_coordinator, equipment_manager, volunteer, check_in_desk, preset_manager, sync_admin, qualifier_admin."
        ),
    )
    created_at: datetime = Field(..., description="When the account was created (UTC).")
    updated_at: datetime = Field(..., description="When the account was last changed (UTC).")
