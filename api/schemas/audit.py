"""Schemas for audit log endpoints."""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    id: int
    user_id: Optional[int] = None
    action: str
    details: Optional[Any] = None  # decoded JSON object, or null
    created_at: datetime


class AuditLogPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[AuditLogEntry]
