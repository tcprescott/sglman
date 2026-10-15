"""The plain acknowledgement body several write endpoints return."""

from pydantic import BaseModel, Field


class DetailResponse(BaseModel):
    detail: str = Field(..., description="A short human-readable confirmation of what happened.")
