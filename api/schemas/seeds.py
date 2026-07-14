"""Schemas for the seed-generation endpoints."""

from typing import Optional

from pydantic import BaseModel, ConfigDict


class RandomizerResponse(BaseModel):
    """A supported randomizer and whether it can embed community triforce texts."""

    model_config = ConfigDict(from_attributes=True)

    randomizer: str
    supports_triforce_texts: bool


class SeedGenerateRequest(BaseModel):
    """Request to roll a seed for a randomizer, optionally from a stored preset."""

    randomizer: str
    preset_id: Optional[int] = None


class SeedResponse(BaseModel):
    """The permalink URL of a freshly generated seed."""

    url: str
