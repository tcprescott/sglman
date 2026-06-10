"""Request/response schemas for personal API token management."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ApiTokenCreateRequest(BaseModel):
    name: str = Field(..., description="A label to recognise this token, e.g. 'OBS overlay'")
    read_only: bool = Field(False, description="Restrict the token to read (GET) endpoints only")
    expires_at: Optional[datetime] = Field(
        None, description="Optional expiry (UTC). Omit for a non-expiring token."
    )


class ApiTokenResponse(BaseModel):
    """A token's metadata. Never includes the secret value."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    token_prefix: str
    read_only: bool
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime


class ApiTokenCreatedResponse(ApiTokenResponse):
    """Returned once at creation; ``token`` is the secret, shown only here."""

    token: str = Field(..., description="The secret token. Copy it now — it cannot be retrieved later.")
