"""Schemas for racetime bot endpoints (global / super-admin).

Responses are built from ``RacetimeBotService.serialize(bot)`` — a secret-free
dict — so ``client_secret`` never appears on the wire.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from models import BotStatus

_CATEGORY = "racetime.gg category slug the bot hosts rooms in. One bot per category."
_CLIENT_ID = "OAuth client id of the bot's racetime.gg application."
_HANDLER = "Dotted path to a custom room handler. Stored for reference; nothing reads it yet."


class RacetimeBotResponse(BaseModel):
    """Mirrors the keys of ``RacetimeBotService.serialize(bot)`` (no secret)."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Bot id.")
    category: str = Field(..., description=_CATEGORY)
    client_id: str = Field(..., description=_CLIENT_ID)
    name: str = Field(..., description="Display name.")
    description: str = Field(..., description="Free-text note. Empty string when unset.")
    is_active: bool = Field(..., description="Whether the bot is switched on.")
    handler_class: str = Field(..., description=_HANDLER + " Empty string when unset.")
    status: BotStatus = Field(
        ...,
        description="Health of the bot's racetime.gg connection: `unknown`, `connected`, `disconnected` or `error`.",
    )
    status_message: str = Field(
        ..., description="Detail behind the last status change, such as an error. Empty string when there is none."
    )


class RacetimeBotCreateRequest(BaseModel):
    category: str = Field(..., description=_CATEGORY + " Must not already have a bot.")
    client_id: str = Field(..., description=_CLIENT_ID)
    client_secret: str = Field(
        ..., description="OAuth client secret. Stored, never returned by any endpoint."
    )
    name: str = Field(..., description="Display name.")
    description: Optional[str] = Field(None, description="Optional free-text note.")
    handler_class: Optional[str] = Field(None, description=_HANDLER)
    is_active: bool = Field(True, description="Whether the bot starts switched on.")


class RacetimeBotUpdateRequest(BaseModel):
    """A partial edit. Omitted fields keep their current value."""

    category: Optional[str] = Field(None, description=_CATEGORY + " Must not clash with another bot's.")
    client_id: Optional[str] = Field(None, description=_CLIENT_ID + " Cannot be empty.")
    client_secret: Optional[str] = Field(
        None, description="Replacement OAuth client secret. Omit to keep the stored one."
    )
    name: Optional[str] = Field(None, description="Display name.")
    description: Optional[str] = Field(None, description="Free-text note.")
    handler_class: Optional[str] = Field(None, description=_HANDLER)
    is_active: Optional[bool] = Field(None, description="Switch the bot on or off.")


class RacetimeBotGrantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Grant id.")
    bot_id: int = Field(..., description="The bot the community may use.")
    tenant_id: int = Field(..., description="The community allowed to use the bot.")
    created_at: datetime = Field(..., description="When the grant was first made (UTC).")


class RacetimeBotGrantRequest(BaseModel):
    tenant_id: int = Field(..., description="Id of the community to allow.")
