"""Audit history, engagement telemetry, and system configuration.

Gates mirror ``api/routers/audit.py`` (admin), ``api/routers/system_config.py``
(staff), and the telemetry service's own staff check.
"""

from datetime import datetime
from typing import List, Optional

from mcp.server.fastmcp import FastMCP

from application.services import AuditService, TelemetryService
from application.tenant_context import require_tenant_id
from application.utils.serialization import decode_json_details
from mcpserver.auth import Gate, current_actor
from mcpserver.registry import register
from mcpserver.schemas import AuditEntry, AuditPage, TenantArg

MAX_ROWS = 500


def _parse(label: str, value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f'{label} must be an ISO 8601 timestamp') from exc


async def list_audit_log(
    tenant: TenantArg = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    user_id: Optional[int] = None,
    action_contains: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> AuditPage:
    """Search the community's audit history — who changed what, and when.

    Requires admin access. Actions are namespaced `verb.object` strings such as
    `match.created`; `action_contains` does a substring match. Times are UTC.
    """
    limit = max(1, min(limit, MAX_ROWS))
    offset = max(0, offset)
    start_dt, end_dt = _parse('start', start), _parse('end', end)

    service = AuditService()
    total = await service.count_logs(
        start=start_dt, end=end_dt, user_id=user_id, action_contains=action_contains,
    )
    logs = await service.list_logs(
        start=start_dt, end=end_dt, user_id=user_id, action_contains=action_contains,
        limit=limit, offset=offset,
    )
    return AuditPage(
        total=total, limit=limit, offset=offset,
        items=[
            AuditEntry(
                id=log.id, user_id=log.user_id, action=log.action,
                details=decode_json_details(log.details), created_at=log.created_at,
            )
            for log in logs
        ],
    )


async def telemetry_summary(
    tenant: TenantArg = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> dict:
    """Engagement totals for a window: events, unique users, sessions, page views.

    Requires staff access.
    """
    actor = current_actor()
    return await TelemetryService().engagement_summary(
        actor.user, start=_parse('start', start), end=_parse('end', end),
    )


async def telemetry_top(
    dimension: str,
    tenant: TenantArg = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 15,
) -> List[dict]:
    """Top engagement rows for one dimension: `paths`, `event_types`, or `users`.

    Requires staff access.
    """
    actor = current_actor()
    limit = max(1, min(limit, 100))
    start_dt, end_dt = _parse('start', start), _parse('end', end)
    service = TelemetryService()
    dispatch = {
        'paths': service.top_paths,
        'event_types': service.top_event_types,
        'users': service.top_users,
    }
    fn = dispatch.get(dimension)
    if fn is None:
        raise ValueError(
            f"Unknown dimension '{dimension}'. Valid: {', '.join(dispatch)}"
        )
    return await fn(actor.user, start=start_dt, end=end_dt, limit=limit)


async def get_system_config(
    tenant: TenantArg = None,
) -> List[dict]:
    """Read the community's system configuration entries.

    Requires staff access.
    """
    from models import SystemConfiguration

    entries = await SystemConfiguration.filter(
        tenant_id=require_tenant_id()
    ).order_by('name')
    return [{'name': e.name, 'value': e.value} for e in entries]


def register_tools(mcp: FastMCP) -> None:
    register(mcp, list_audit_log, gate=Gate.ADMIN, title='Search audit log')
    register(mcp, telemetry_summary, gate=Gate.STAFF, title='Telemetry summary')
    register(mcp, telemetry_top, gate=Gate.STAFF, title='Telemetry leaderboards')
    register(mcp, get_system_config, gate=Gate.STAFF, title='Get system config')
