"""Audit log endpoints (read, admin only)."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.dependencies import ServiceErrorRoute, require_staff
from api.schemas.audit import AuditLogEntry, AuditLogPage
from application.services import AuditService
from application.utils.serialization import decode_json_details
from models import User

router = APIRouter(prefix="/audit-logs", tags=["Audit"], route_class=ServiceErrorRoute)


# Shared with the MCP audit tool so both surfaces decode details identically.
_decode_details = decode_json_details


@router.get(
    "",
    response_model=AuditLogPage,
    summary="List audit log entries",
    description=(
        "Returns the community's audit log newest first, one page at a time, with the total count of "
        "matching entries so you can page through with `limit` and `offset`.\n\n"
        "**Who can call this:** Staff."
    ),
)
async def list_audit_logs(
    start: Optional[datetime] = Query(None, description="Only entries at or after this time (UTC ISO 8601)."),
    end: Optional[datetime] = Query(None, description="Only entries at or before this time (UTC ISO 8601)."),
    user_id: Optional[int] = Query(None, description="Only entries performed by this user ID."),
    action_contains: Optional[str] = Query(None, description="Only entries whose action contains this text, ignoring case."),
    limit: int = Query(100, ge=1, le=500, description="Maximum entries to return."),
    offset: int = Query(0, ge=0, description="Entries to skip before this page."),
    actor: User = Depends(require_staff),
):
    service = AuditService()
    total = await service.count_logs(
        actor=actor, start=start, end=end, user_id=user_id, action_contains=action_contains,
    )
    logs = await service.list_logs(
        actor=actor, start=start, end=end, user_id=user_id, action_contains=action_contains,
        limit=limit, offset=offset,
    )
    items = [
        AuditLogEntry(
            id=log.id,
            user_id=log.user_id,
            action=log.action,
            details=_decode_details(log.details),
            created_at=log.created_at,
        )
        for log in logs
    ]
    return AuditLogPage(total=total, limit=limit, offset=offset, items=items)
