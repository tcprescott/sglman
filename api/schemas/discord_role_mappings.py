"""Schemas for Discord-role-to-app-role mapping endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from models import Role


class DiscordRoleMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    guild_id: int
    discord_role_id: int
    discord_role_name: str
    app_role: Role
    created_at: datetime
    updated_at: datetime


class DiscordRoleMappingCreate(BaseModel):
    guild_id: int
    discord_role_id: int
    discord_role_name: str
    app_role: Role
