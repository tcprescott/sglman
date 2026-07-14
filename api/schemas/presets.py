"""Schemas for preset endpoints."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class PresetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    randomizer: str
    settings: Dict[str, Any]
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PresetCreateRequest(BaseModel):
    name: str
    randomizer: str
    settings: Dict[str, Any]
    description: Optional[str] = None


class PresetUpdateRequest(BaseModel):
    name: Optional[str] = None
    randomizer: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
