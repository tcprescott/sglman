"""Schemas for staff-managed outbound webhook endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class WebhookResponse(BaseModel):
    """A webhook as returned by list/GET — never includes the secret."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    event_types: List[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WebhookCreatedResponse(WebhookResponse):
    """Returned once on create/regenerate; carries the signing secret."""

    secret: str


class WebhookSecretResponse(BaseModel):
    secret: str


class WebhookCreate(BaseModel):
    name: str = Field(..., description="Human-readable label")
    url: str = Field(..., description="HTTPS endpoint that receives the POST")
    event_types: List[str] = Field(
        ..., description="Event names to deliver, or ['*'] for all"
    )
    is_active: bool = True


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    event_types: Optional[List[str]] = None
    is_active: Optional[bool] = None


class WebhookDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    webhook_id: int
    event_type: str
    response_status: Optional[int]
    attempt_count: int
    success: bool
    error: Optional[str]
    created_at: datetime
    delivered_at: Optional[datetime]
