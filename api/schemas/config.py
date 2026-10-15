"""Schemas for system configuration endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class ConfigEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., description="The setting's key.")
    value: str = Field(..., description="The stored value, always as a string.")


class ConfigValueUpdate(BaseModel):
    value: str = Field(
        ...,
        description=(
            "New value for the setting, as a string. It's checked and normalised for the key, "
            "for example `yes` becomes `true` on a switch."
        ),
    )
