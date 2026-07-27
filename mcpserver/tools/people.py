"""People: users, their roles, and match crew.

Gates mirror ``api/routers/users.py`` and ``api/routers/crew.py``, with one
deliberate difference at :func:`list_match_crew` — documented at the tool.
"""

from typing import List, Optional

from mcp.server.fastmcp import FastMCP

from api._match_view import MATCH_PREFETCH
from application.errors import require_found
from application.services import AuthService, ReportsService, UserService
from application.tenant_context import require_tenant_id
from mcpserver.auth import Gate, current_actor
from mcpserver.registry import register
from mcpserver.schemas import (
    CrewMemberInfo,
    MatchCrew,
    TenantArg,
    UserDetail,
    UserSummary,
)


async def list_users(
    tenant: TenantArg = None,
    role: Optional[str] = None,
    has_discord: bool = False,
) -> List[UserSummary]:
    """List the community's users, optionally filtered to holders of one role.

    Requires staff access. `role` is a role name such as `staff` or `proctor`.
    """
    from models import Role

    parsed: Optional[Role] = None
    if role:
        try:
            parsed = Role(role.lower())
        except ValueError as exc:
            valid = ', '.join(r.value for r in Role)
            raise ValueError(f"Unknown role '{role}'. Valid roles: {valid}") from exc
    users = await UserService().get_all_users(role=parsed, has_discord=has_discord)
    return [UserSummary.model_validate(u, from_attributes=True) for u in users]


async def get_user(
    user_id: int,
    tenant: TenantArg = None,
) -> UserDetail:
    """Get one user's profile and the roles they hold in this community.

    You may always read your own record; reading anyone else's requires staff
    access, matching the REST API.
    """
    actor = current_actor()
    if user_id != actor.user.id and not await AuthService.is_staff(actor.user):
        raise PermissionError('Staff access required to view another user')
    user = require_found(await UserService().get_user_by_id(user_id), 'User')
    roles = await AuthService.get_roles(user)
    detail = UserDetail.model_validate(user, from_attributes=True)
    detail.roles = sorted(r.value for r in roles)
    return detail


async def list_match_crew(
    match_id: int,
    tenant: TenantArg = None,
) -> MatchCrew:
    """List a match's commentators and trackers, including pending signups.

    Requires admin access. `get_match` deliberately hides unapproved crew from
    everyone; this is the coordinator's view of who has actually volunteered, so
    it sits behind a higher gate than the match itself.
    """
    from models import Match

    match = require_found(
        await Match.filter(id=match_id, tenant_id=require_tenant_id())
        .prefetch_related(*MATCH_PREFETCH)
        .first(),
        'Match',
    )

    def to_info(row) -> CrewMemberInfo:
        return CrewMemberInfo(
            id=row.id,
            user=(
                UserSummary.model_validate(row.user, from_attributes=True)
                if row.user else None
            ),
            approved=row.approved,
            acknowledged_at=getattr(row, 'acknowledged_at', None),
        )

    return MatchCrew(
        match_id=match.id,
        commentators=[to_info(c) for c in match.commentators],
        trackers=[to_info(t) for t in match.trackers],
    )


async def crew_coverage_report(
    start: str,
    end: str,
    tenant: TenantArg = None,
    tournament_id: Optional[int] = None,
    approved_only: bool = False,
) -> dict:
    """Crew coverage across a window: which matches have commentary and tracking.

    Requires admin access. `start` and `end` are ISO 8601 timestamps.
    """
    from datetime import datetime

    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except ValueError as exc:
        raise ValueError('start and end must be ISO 8601 timestamps') from exc
    return await ReportsService().crew_coverage(
        start=start_dt, end=end_dt,
        tournament_id=tournament_id, approved_only=approved_only,
    )


def register_tools(mcp: FastMCP) -> None:
    register(mcp, list_users, gate=Gate.STAFF, title='List users')
    register(mcp, get_user, gate=Gate.ACTOR, title='Get user')
    register(mcp, list_match_crew, gate=Gate.ADMIN, title='List match crew')
    register(mcp, crew_coverage_report, gate=Gate.ADMIN, title='Crew coverage report')
