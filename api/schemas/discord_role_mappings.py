"""Schemas for Discord-role-to-app-role mapping endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from models import Role, TournamentGrant


class DiscordRoleMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    guild_id: int
    discord_role_id: int
    discord_role_name: str
    app_role: Optional[Role] = None
    tournament_grant: Optional[TournamentGrant] = None
    tournament_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class DiscordRoleMappingCreate(BaseModel):
    """Exactly one of ``app_role`` / ``tournament_grant`` is set; the latter
    additionally requires ``tournament_id``. The service enforces both rules and
    raises a 400 rather than duplicating the check here, so the REST and UI
    surfaces cannot drift."""

    guild_id: int
    discord_role_id: int
    discord_role_name: str
    app_role: Optional[Role] = None
    tournament_grant: Optional[TournamentGrant] = None
    tournament_id: Optional[int] = None
