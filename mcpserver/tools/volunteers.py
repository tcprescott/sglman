"""Volunteer shifts and coverage.

The roster tools are gated at **admin**, one step above their REST counterparts
(``api/routers/volunteers.py`` reads at ``require_api_actor``). That is a
deliberate divergence, not an oversight: the REST reads back a self-service UI
where a volunteer looks at their own schedule, whereas a single call here hands
back a whole window's roster with names attached. Bulk disclosure of who is
where and when is a different thing from a person checking their own shift, so
it sits behind the coordinator's gate.

``my_volunteer_shifts`` is the self-service exception, at **actor**: it reads
back only the caller's own published shifts, the same as
``GET /volunteers/me/assignments``.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from mcp.server.mcpserver import MCPServer

from application.services import AnalyticsService
from application.services.volunteer.volunteer_position_service import (
    VolunteerPositionService,
)
from application.services.volunteer.volunteer_schedule_service import (
    VolunteerScheduleService,
)
from mcpserver.auth import Gate, current_actor
from mcpserver.registry import register
from mcpserver.schemas import MyShift, ShiftSummary, TenantArg, VolunteerPositionInfo
from mcpserver.tools._args import window as _window
from models import FeatureFlag


async def list_volunteer_shifts(
    start: str,
    end: str,
    tenant: TenantArg = None,
) -> List[ShiftSummary]:
    """List volunteer shifts in a window, with who is assigned to each.

    Requires admin access. `start` and `end` are ISO 8601 timestamps (UTC).
    """
    start_dt, end_dt = _window(start, end)
    shifts = await VolunteerScheduleService().list_shifts_for_window(start_dt, end_dt)
    out: List[ShiftSummary] = []
    for shift in shifts:
        assignments = list(shift.assignments)
        out.append(ShiftSummary(
            id=shift.id,
            position=shift.position.name if shift.position else None,
            starts_at=shift.starts_at,
            ends_at=shift.ends_at,
            slots_needed=shift.slots_needed,
            filled=len(assignments),
            assignees=[
                a.user.preferred_name for a in assignments if getattr(a, 'user', None)
            ],
        ))
    return out


async def volunteer_coverage(
    start: str,
    end: str,
    tenant: TenantArg = None,
) -> List[Dict[str, Any]]:
    """Per-shift filled-versus-needed counts across a window — where the gaps are.

    Requires admin access.
    """
    start_dt, end_dt = _window(start, end)
    return await VolunteerScheduleService().coverage(start_dt, end_dt)


async def volunteer_hour_trends(
    start: str,
    end: str,
    tenant: TenantArg = None,
    bucket: str = 'week',
) -> Dict[str, Any]:
    """Scheduled versus checked-in volunteer hours over time, and the fill rate.

    Requires admin access. `bucket` is `week` or `month`. A shift contributes
    `duration × assignees` scheduled hours to the bucket it starts in; fill rate
    measures those against the hours the roster actually needed.

    This lives behind the volunteers flag even though it is served by the
    analytics service, which carries no flag of its own — a community with
    volunteers switched off must not be able to read its volunteer hours here.
    """
    start_dt, end_dt = _window(start, end)
    return await AnalyticsService().volunteer_hour_trends(
        start=start_dt, end=end_dt, bucket=bucket,
    )


async def list_volunteer_positions(
    tenant: TenantArg = None,
    active_only: bool = False,
) -> List[VolunteerPositionInfo]:
    """List the volunteer jobs a community schedules — the names shifts hang off.

    Requires admin access. Set `active_only` to skip retired positions.
    """
    service = VolunteerPositionService()
    positions = await (service.list_active() if active_only else service.list_all())
    return [
        VolunteerPositionInfo.model_validate(p, from_attributes=True) for p in positions
    ]


async def my_volunteer_shifts(
    tenant: TenantArg = None,
    upcoming_only: bool = True,
) -> List[MyShift]:
    """Your own volunteer shifts, soonest first.

    Only published shifts: an auto-scheduler draft you haven't been told about
    stays hidden. Set `upcoming_only` to false to include finished shifts.
    """
    after = datetime.now(timezone.utc) if upcoming_only else None
    assignments = await VolunteerScheduleService().assignments_for_user(
        current_actor().user, upcoming_after=after,
    )
    return [
        MyShift(
            assignment_id=a.id,
            shift_id=a.shift_id,  # type: ignore[attr-defined]
            position=a.shift.position.name if a.shift.position else None,
            label=a.shift.label,
            starts_at=a.shift.starts_at,
            ends_at=a.shift.ends_at,
            acknowledged_at=a.acknowledged_at,
            checked_in_at=a.checked_in_at,
        )
        for a in assignments
    ]


def register_tools(mcp: MCPServer) -> None:
    register(
        mcp, my_volunteer_shifts, gate=Gate.ACTOR,
        feature=FeatureFlag.VOLUNTEERS, title='My volunteer shifts',
    )
    register(
        mcp, list_volunteer_positions, gate=Gate.ADMIN,
        feature=FeatureFlag.VOLUNTEERS, title='List volunteer positions',
    )
    register(
        mcp, list_volunteer_shifts, gate=Gate.ADMIN,
        feature=FeatureFlag.VOLUNTEERS, title='List volunteer shifts',
    )
    register(
        mcp, volunteer_coverage, gate=Gate.ADMIN,
        feature=FeatureFlag.VOLUNTEERS, title='Volunteer coverage',
    )
    register(
        mcp, volunteer_hour_trends, gate=Gate.ADMIN,
        feature=FeatureFlag.VOLUNTEERS, title='Volunteer hour trends',
    )
