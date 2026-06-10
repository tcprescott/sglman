"""Schemas shared across multiple API domains."""

from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    """Public identity fields for a user appearing in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: Optional[str] = None
    discord_id: Optional[int] = None
    pronouns: Optional[str] = None
