"""Schemas for stage endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class StageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    stream_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
