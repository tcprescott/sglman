"""Schemas for racetime bot endpoints (global / super-admin).

Responses are built from ``RacetimeBotService.serialize(bot)`` — a secret-free
dict — so ``client_secret`` never appears on the wire.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from models import BotStatus


class RacetimeBotResponse(BaseModel):
    """Mirrors the keys of ``RacetimeBotService.serialize(bot)`` (no secret)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    client_id: str
    name: str
    description: str
    is_active: bool
    handler_class: str
    status: BotStatus
    status_message: str


class RacetimeBotCreateRequest(BaseModel):
    category: str
    client_id: str
    client_secret: str
    name: str
    description: Optional[str] = None
    handler_class: Optional[str] = None
    is_active: bool = True


class RacetimeBotUpdateRequest(BaseModel):
    category: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    handler_class: Optional[str] = None
    is_active: Optional[bool] = None


class RacetimeBotGrantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bot_id: int
    tenant_id: int
    created_at: datetime


class RacetimeBotGrantRequest(BaseModel):
    tenant_id: int
