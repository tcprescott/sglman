"""Audit log endpoints (read, admin only)."""

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.dependencies import ServiceErrorRoute, require_admin
from api.schemas.audit import AuditLogEntry, AuditLogPage
from application.services import AuditService
from models import AuditLog, User

router = APIRouter(prefix="/audit-logs", tags=["Audit"], route_class=ServiceErrorRoute)


def _decode_details(raw: Optional[str]):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


@router.get(
    "",
    response_model=AuditLogPage,
    summary="List audit log entries",
    description="Requires admin access. Supports filtering and pagination.",
)
async def list_audit_logs(
    start: Optional[datetime] = Query(None, description="Only entries at or after this time"),
    end: Optional[datetime] = Query(None, description="Only entries at or before this time"),
    user_id: Optional[int] = Query(None, description="Only entries by this user"),
    action_contains: Optional[str] = Query(None, description="Substring match on the action string"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    actor: User = Depends(require_admin),
):
    service = AuditService()
    total = await service.count_logs(
        start=start, end=end, user_id=user_id, action_contains=action_contains,
    )
    logs = await service.list_logs(
        start=start, end=end, user_id=user_id, action_contains=action_contains,
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
