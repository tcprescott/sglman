"""Request schemas for user & role write actions."""

from typing import List, Optional

from pydantic import BaseModel, Field

from models import Role


class UserCreateRequest(BaseModel):
    username: str
    discord_id: int = Field(..., description="Discord user ID (required and unique)")
    display_name: Optional[str] = None
    pronouns: Optional[str] = None
    is_active: bool = True


class UserSelfUpdate(BaseModel):
    display_name: Optional[str] = None
    pronouns: Optional[str] = None
    dm_notifications: Optional[bool] = None


class UserProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    pronouns: Optional[str] = None


class UserAdminUpdate(BaseModel):
    is_active: Optional[bool] = None


class RoleRequest(BaseModel):
    role: Role = Field(..., description="One of: staff, proctor, stream_manager")


class TournamentEnrollmentUpdate(BaseModel):
    tournament_ids: List[int] = Field(..., description="The full set of tournaments the user is enrolled in")
