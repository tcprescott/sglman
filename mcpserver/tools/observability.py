"""Audit history, engagement telemetry, integrations, and system configuration.

Gates mirror ``api/routers/audit.py`` (admin), ``api/routers/system_config.py``
(staff), ``api/routers/webhooks.py`` (staff), ``api/routers/service_health.py``
(staff for the tenant subset), and the telemetry service's own staff check.

``list_feedback`` mirrors ``api/routers/feedback.py``'s staff queue and carries
that router's ``FEEDBACK`` flag. ``FeedbackService`` refuses a community with
the feature off regardless, but declaring the flag here is what hides the tool
instead of letting a model discover the refusal a round-trip later.
"""

from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from application.services import (
    AuditService,
    FeedbackService,
    ServiceHealthService,
    TelemetryService,
    WebhookService,
)
from application.tenant_context import require_tenant_id
from application.utils.serialization import decode_json_details
from mcpserver.auth import Gate, current_actor
from mcpserver.registry import register
from mcpserver.schemas import (
    AuditEntry,
    AuditPage,
    FeedbackEntry,
    ServiceHealthProbe,
    TenantArg,
    WebhookDeliveryInfo,
    WebhookInfo,
)
from mcpserver.tools._args import choose, clamp, parse_ts
from models import FeatureFlag

MAX_ROWS = 500


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
    limit = clamp(limit, low=1, high=MAX_ROWS)
    offset = max(0, offset)
    start_dt, end_dt = parse_ts('start', start), parse_ts('end', end)

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
) -> Dict[str, Any]:
    """Engagement totals for a window: events, unique users, sessions, page views.

    Requires staff access.
    """
    actor = current_actor()
    return await TelemetryService().engagement_summary(
        actor.user, start=parse_ts('start', start), end=parse_ts('end', end),
    )


async def telemetry_top(
    dimension: str,
    tenant: TenantArg = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """Top engagement rows for one dimension: `paths`, `event_types`, or `users`.

    Requires staff access.
    """
    actor = current_actor()
    limit = clamp(limit, low=1, high=100)
    start_dt, end_dt = parse_ts('start', start), parse_ts('end', end)
    service = TelemetryService()
    fn = choose(dimension, {
        'paths': service.top_paths,
        'event_types': service.top_event_types,
        'users': service.top_users,
    })
    return await fn(actor.user, start=start_dt, end=end_dt, limit=limit)


async def get_system_config(
    tenant: TenantArg = None,
) -> List[Dict[str, Any]]:
    """Read the community's system configuration entries.

    Requires staff access.
    """
    from models import SystemConfiguration

    entries = await SystemConfiguration.filter(
        tenant_id=require_tenant_id()
    ).order_by('name')
    return [{'name': e.name, 'value': e.value} for e in entries]


async def list_service_health(
    tenant: TenantArg = None,
) -> List[ServiceHealthProbe]:
    """Check the community's own integrations: its racetime bots and Challonge link.

    Requires staff access. Probed live, so this is current rather than cached.
    This is the tenant subset — the platform-wide board is a super-admin surface
    and is not exposed here.
    """
    probes = await ServiceHealthService().tenant_subset(require_tenant_id())
    return [
        ServiceHealthProbe(
            key=probe.key,
            label=probe.label,
            category=probe.category,
            status=getattr(probe.status, 'value', probe.status),
            message=probe.message,
            checked_at=probe.checked_at,
        )
        for probe in probes
    ]


async def list_webhooks(
    tenant: TenantArg = None,
) -> List[WebhookInfo]:
    """List the community's outbound webhooks and the events each subscribes to.

    Requires staff access. Signing secrets are never returned.
    """
    hooks = await WebhookService().list_webhooks(current_actor().user)
    return [
        WebhookInfo(
            id=hook.id,
            name=hook.name,
            url=hook.url,
            event_types=list(hook.event_types or []),
            is_active=hook.is_active,
        )
        for hook in hooks
    ]


async def list_webhook_deliveries(
    webhook_id: int,
    tenant: TenantArg = None,
    limit: int = 50,
    offset: int = 0,
) -> List[WebhookDeliveryInfo]:
    """List recent delivery attempts for one webhook — what fired, and what failed.

    Requires staff access. The serialized request payload is omitted; use
    `list_audit_log` for what the underlying change was.
    """
    deliveries = await WebhookService().list_deliveries(
        current_actor().user, webhook_id,
        limit=clamp(limit, low=1, high=MAX_ROWS), offset=max(0, offset),
    )
    return [
        WebhookDeliveryInfo(
            id=row.id,
            event_type=row.event_type,
            success=row.success,
            response_status=row.response_status,
            attempt_count=row.attempt_count,
            error=row.error,
            created_at=row.created_at,
            delivered_at=row.delivered_at,
        )
        for row in deliveries
    ]


async def list_feedback(
    tenant: TenantArg = None,
    limit: int = 50,
) -> List[FeedbackEntry]:
    """List feedback users submitted from the site, most recent first.

    Requires staff access.
    """
    rows = await FeedbackService().list_recent(limit=clamp(limit, low=1, high=MAX_ROWS))
    return [
        FeedbackEntry(
            id=row.id,
            category=getattr(row.category, 'value', row.category),
            status=getattr(row.status, 'value', row.status),
            message=row.message,
            page_url=row.page_url,
            submitted_by=row.user.preferred_name if row.user else None,
            created_at=row.created_at,
        )
        for row in rows
    ]


def register_tools(mcp: FastMCP) -> None:
    register(mcp, list_audit_log, gate=Gate.ADMIN, title='Search audit log')
    register(mcp, telemetry_summary, gate=Gate.STAFF, title='Telemetry summary')
    register(mcp, telemetry_top, gate=Gate.STAFF, title='Telemetry leaderboards')
    register(mcp, get_system_config, gate=Gate.STAFF, title='Get system config')
    register(mcp, list_service_health, gate=Gate.STAFF, title='Service health')
    register(mcp, list_webhooks, gate=Gate.STAFF, title='List webhooks')
    register(
        mcp, list_webhook_deliveries, gate=Gate.STAFF,
        title='List webhook deliveries',
    )
    register(
        mcp, list_feedback, gate=Gate.STAFF,
        feature=FeatureFlag.FEEDBACK, title='List feedback',
    )
