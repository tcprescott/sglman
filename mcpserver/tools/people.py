"""People: users, their roles, and match crew.

Gates mirror ``api/routers/users.py`` and ``api/routers/crew.py``, with one
deliberate difference at :func:`list_match_crew` — documented at the tool.
"""

from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from api._match_view import MATCH_PREFETCH
from application.errors import require_found
from application.services import (
    AuthService,
    PlayerAvailabilityService,
    ReportsService,
    UserService,
)
from application.tenant_context import require_tenant_id
from mcpserver.auth import Gate, current_actor
from mcpserver.registry import register
from mcpserver.schemas import (
    AvailabilityWindow,
    CrewMemberInfo,
    MatchCrew,
    PlayerAvailability,
    TenantArg,
    UserDetail,
    UserSummary,
)
from mcpserver.tools._args import window as _window

# A scheduling question asks about a squad, not a census. The cap keeps one call
# from turning into a whole-community availability dump.
MAX_AVAILABILITY_USERS = 50


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
    # The community's members, not the platform's user table — a session
    # resolves one tenant and every other tool here is community-scoped.
    users = await UserService().get_community_people(role=parsed, has_discord=has_discord)
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
) -> Dict[str, Any]:
    """Crew coverage across a window: which matches have commentary and tracking.

    Requires admin access. `start` and `end` are ISO 8601 timestamps.
    """
    start_dt, end_dt = _window(start, end)
    return await ReportsService().crew_coverage(
        start=start_dt, end=end_dt,
        tournament_id=tournament_id, approved_only=approved_only,
    )


async def get_player_availability(
    start: str,
    end: str,
    tenant: TenantArg = None,
    user_ids: Optional[List[int]] = None,
) -> List[PlayerAvailability]:
    """When players said they can play, across a window.

    `start` and `end` are ISO 8601 timestamps. Defaults to your own windows;
    naming other players requires staff access, matching `get_user`. A player
    with no declared windows is returned with an empty list rather than omitted,
    so "has not answered" is distinguishable from "not asked about".
    """
    actor = current_actor()
    start_dt, end_dt = _window(start, end)
    wanted = list(dict.fromkeys(user_ids or [actor.user.id]))
    if len(wanted) > MAX_AVAILABILITY_USERS:
        raise ValueError(
            f'user_ids is limited to {MAX_AVAILABILITY_USERS} players per call'
        )
    if wanted != [actor.user.id] and not await AuthService.is_staff(actor.user):
        raise PermissionError("Staff access required to view other players' availability")

    service = UserService()
    windows_by_user = await PlayerAvailabilityService().availability_map(
        wanted, start_dt, end_dt,
    )
    out: List[PlayerAvailability] = []
    for user_id in wanted:
        user = await service.get_user_by_id(user_id)
        out.append(PlayerAvailability(
            user_id=user_id,
            name=user.preferred_name if user else None,
            windows=[
                AvailabilityWindow(
                    starts_at=row.starts_at,
                    ends_at=row.ends_at,
                    status=getattr(row.status, 'value', row.status),
                    note=row.note,
                )
                for row in windows_by_user.get(user_id, [])
            ],
        ))
    return out


def register_tools(mcp: FastMCP) -> None:
    register(mcp, list_users, gate=Gate.STAFF, title='List users')
    register(mcp, get_user, gate=Gate.ACTOR, title='Get user')
    register(
        mcp, get_player_availability, gate=Gate.ACTOR,
        title='Get player availability',
    )
    register(mcp, list_match_crew, gate=Gate.ADMIN, title='List match crew')
    register(mcp, crew_coverage_report, gate=Gate.ADMIN, title='Crew coverage report')
