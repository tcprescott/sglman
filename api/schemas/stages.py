"""Schemas for stage endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="The stage's ID.")
    name: str = Field(..., description="The stage's name, unique within the community.")
    stream_url: Optional[str] = Field(None, description="Link to the stream this stage broadcasts on.")
    is_active: bool = Field(..., description="Whether the stage is in use. Inactive stages are left off the watch page and the reports.")
    created_at: datetime = Field(..., description="When the stage was created (UTC).")
    updated_at: datetime = Field(..., description="When the stage was last changed (UTC).")
