"""Request schemas for stream room write actions."""

from typing import Optional

from pydantic import BaseModel


class StreamRoomCreateRequest(BaseModel):
    name: str
    stream_url: Optional[str] = None
    is_active: bool = True


class StreamRoomUpdateRequest(BaseModel):
    name: Optional[str] = None
    stream_url: Optional[str] = None
    is_active: Optional[bool] = None
