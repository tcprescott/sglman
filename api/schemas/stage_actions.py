"""Request schemas for stage write actions."""

from typing import Optional

from pydantic import BaseModel, Field


class StageCreateRequest(BaseModel):
    name: str = Field(..., description="The stage's name. Can't be blank and must be unique in the community.")
    stream_url: Optional[str] = Field(None, description="Link to the stage's stream. Must be http or https.")
    is_active: bool = Field(True, description="Whether the stage starts out in use.")


class StageUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, description="New name. Can't be blank. Omit to leave it unchanged.")
    stream_url: Optional[str] = Field(
        None,
        description=(
            "New stream link, http or https. An empty string clears it. Omit to leave it unchanged."
        ),
    )
    is_active: Optional[bool] = Field(None, description="Set false to retire the stage instead of deleting it. Omit to leave it unchanged.")
