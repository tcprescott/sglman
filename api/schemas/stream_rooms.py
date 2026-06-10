"""Schemas for stream room endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class StreamRoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    stream_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
