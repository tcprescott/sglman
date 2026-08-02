"""Request schemas for stage write actions."""

from typing import Optional

from pydantic import BaseModel


class StageCreateRequest(BaseModel):
    name: str
    stream_url: Optional[str] = None
    is_active: bool = True


class StageUpdateRequest(BaseModel):
    name: Optional[str] = None
    stream_url: Optional[str] = None
    is_active: Optional[bool] = None
