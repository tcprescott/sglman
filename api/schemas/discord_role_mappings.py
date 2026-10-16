"""Schemas for Discord-role-to-app-role mapping endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.snowflake import Snowflake
from models import Role, TournamentGrant

_APP_ROLE = (
    "Community-wide role the Discord role grants: `staff`, `proctor`, `stream_manager`, "
    "`triforce_submitter`, `volunteer_coordinator`, `equipment_manager`, `volunteer`, `check_in_desk`, "
    "`preset_manager`, `sync_admin` or `qualifier_admin`."
)
_GRANT = "Per-tournament authority the Discord role grants: `tournament_admin` or `crew_coordinator`."


class DiscordRoleMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID of the mapping.")
    guild_id: Snowflake = Field(..., description="ID of the Discord server the role belongs to, as a string.")
    discord_role_id: Snowflake = Field(..., description="ID of the Discord role, as a string.")
    discord_role_name: str = Field(..., description="Name of the Discord role, as recorded when the mapping was made.")
    app_role: Optional[Role] = Field(None, description=f"{_APP_ROLE} Null when the mapping is a tournament grant.")
    tournament_grant: Optional[TournamentGrant] = Field(
        None, description=f"{_GRANT} Null when the mapping grants a community-wide role."
    )
    tournament_id: Optional[int] = Field(
        None, description="ID of the tournament a tournament grant applies to; null for a community-wide role."
    )
    created_at: datetime = Field(..., description="When the mapping was created (UTC).")
    updated_at: datetime = Field(..., description="When the mapping was last changed (UTC).")


class DiscordRoleMappingCreate(BaseModel):
    """Exactly one of ``app_role`` / ``tournament_grant`` is set; the latter
    additionally requires ``tournament_id``. The service enforces both rules and
    raises a 400 rather than duplicating the check here, so the REST and UI
    surfaces cannot drift."""

    guild_id: Snowflake = Field(..., description="ID of the Discord server the role belongs to, as a string.")
    discord_role_id: Snowflake = Field(..., description="ID of the Discord role, as a string.")
    discord_role_name: str = Field(..., description="Name of the Discord role, for display.")
    app_role: Optional[Role] = Field(
        None, description=f"{_APP_ROLE} Set this or `tournament_grant`, not both. `super_admin` is refused."
    )
    tournament_grant: Optional[TournamentGrant] = Field(
        None, description=f"{_GRANT} Set this or `app_role`, not both. Needs `tournament_id`."
    )
    tournament_id: Optional[int] = Field(
        None, description="Tournament a `tournament_grant` applies to. Leave empty with `app_role`."
    )
