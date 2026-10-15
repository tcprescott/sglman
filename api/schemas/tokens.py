"""Request/response schemas for personal API token management."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ApiTokenCreateRequest(BaseModel):
    name: str = Field(..., description="A label to recognise this token by, such as \"OBS overlay\". Can't be blank.")
    read_only: bool = Field(False, description="Restrict the token to read (GET) endpoints only.")
    expires_at: Optional[datetime] = Field(
        None,
        description=(
            "When the token stops working (UTC). Must be in the future. Omit for a token that "
            "doesn't expire. A token created with an expiring token never outlives it, so its "
            "expiry is capped at the parent's."
        ),
    )


class ApiTokenResponse(BaseModel):
    """A token's metadata. Never includes the secret value."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="The token's ID, used to revoke it.")
    name: str = Field(..., description="The label given to the token.")
    token_prefix: str = Field(..., description="The first characters of the secret, to tell tokens apart.")
    read_only: bool = Field(..., description="Whether the token is limited to read (GET) endpoints.")
    last_used_at: Optional[datetime] = Field(None, description="When the token was last used (UTC). Null if never.")
    expires_at: Optional[datetime] = Field(None, description="When the token stops working (UTC). Null if it doesn't expire.")
    created_at: datetime = Field(..., description="When the token was created (UTC).")


class ApiTokenCreatedResponse(ApiTokenResponse):
    """Returned once at creation; ``token`` is the secret, shown only here."""

    token: str = Field(..., description="The secret token. Copy it now — it cannot be retrieved later.")
