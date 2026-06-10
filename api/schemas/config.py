"""Schemas for system configuration endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class ConfigEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    value: str


class ConfigValueUpdate(BaseModel):
    value: str = Field(..., description="New value for the configuration key")
