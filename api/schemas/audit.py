"""Schemas for audit log endpoints."""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    id: int = Field(..., description="ID of the audit entry.")
    user_id: Optional[int] = Field(None, description="ID of the person who performed the action.")
    action: str = Field(
        ..., description="What happened, as a namespaced `verb.object` string such as `match.created`."
    )
    details: Optional[Any] = Field(
        None,
        description=(
            "Action-specific context, usually a JSON object. Older entries that weren't stored as JSON "
            "come back as a plain string; null when the entry has none."
        ),
    )
    created_at: datetime = Field(..., description="When the action happened (UTC).")


class AuditLogPage(BaseModel):
    total: int = Field(..., description="Entries matching the filters, across all pages.")
    limit: int = Field(..., description="Page size used for this response.")
    offset: int = Field(..., description="Entries skipped before this page.")
    items: List[AuditLogEntry] = Field(..., description="This page of entries, newest first.")
