"""Match and schedule reads.

The list/detail split here is deliberate and is the main design decision in the
tool catalogue:

* ``get_match`` reuses ``api/_match_view.serialize_match``, so the rule baked
  into it — unapproved crew are never disclosed — cannot drift between the REST
  API and this surface. That rule is exactly the kind that decays when two
  serializers exist.
* ``list_matches`` returns a compact shape instead. A hundred full match records
  is mostly padding, and padding is the expensive kind of wrong for an LLM
  consumer: it buries the answer and burns the context the model needs to reason.
"""

from datetime import datetime
from typing import List, Optional

from mcp.server.fastmcp import FastMCP

from api._match_view import MATCH_PREFETCH, serialize_match
from api.schemas.matches import MatchResponse
from application.errors import require_found
from application.services import MatchService, ReportsService
from application.services.match.match_status import resolve as resolve_status
from application.tenant_context import require_tenant_id
from mcpserver.auth import Gate
from mcpserver.registry import register
from mcpserver.schemas import MatchSummary, StreamRoomBlock, TenantArg

# One page of matches. The cap is not politeness: an unbounded list is how a
# tool call silently becomes 200k tokens and the model loses the thread.
MAX_MATCHES = 200


def _summarize(match) -> MatchSummary:
    return MatchSummary(
        id=match.id,
        tournament=match.tournament.name if match.tournament else None,
        scheduled_at=match.scheduled_at,
        status=resolve_status(match=match).value,
        players=[p.user.preferred_name for p in match.players if p.user],
        stream_room=match.stream_room.name if match.stream_room else None,
        restream_url=match.stream_room.stream_url if match.stream_room else None,
    )


async def list_matches(
    tenant: TenantArg = None,
    tournament_id: Optional[List[int]] = None,
    stream_room_id: Optional[List[int]] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 50,
) -> List[MatchSummary]:
    """List matches, filtered by tournament, stream room, and scheduled window.

    Returns a compact summary per match, ordered by scheduled time. Use
    `get_match` for full detail on one. Times are UTC.
    """
    from models import Match

    limit = max(1, min(limit, MAX_MATCHES))
    query = Match.filter(tenant_id=require_tenant_id())
    if tournament_id:
        query = query.filter(tournament_id__in=tournament_id)
    if stream_room_id:
        query = query.filter(stream_room_id__in=stream_room_id)
    if start is not None:
        query = query.filter(scheduled_at__gte=start)
    if end is not None:
        query = query.filter(scheduled_at__lte=end)
    matches = await (
        query.prefetch_related(*MATCH_PREFETCH).order_by('scheduled_at').limit(limit)
    )
    return [_summarize(m) for m in matches]


async def get_match(
    match_id: int,
    tenant: TenantArg = None,
) -> MatchResponse:
    """Get full detail for one match: players, seed, stream room, and crew.

    Only approved crew are listed. Use `list_match_crew` (admin) to see pending
    signups as well.
    """
    from models import Match

    match = require_found(
        await Match.filter(id=match_id, tenant_id=require_tenant_id())
        .prefetch_related(*MATCH_PREFETCH)
        .first(),
        'Match',
    )
    return serialize_match(match)


async def get_schedule(
    date: str,
    tenant: TenantArg = None,
) -> List[StreamRoomBlock]:
    """Get one day's schedule, grouped by stream room.

    `date` is YYYY-MM-DD, interpreted in the community's local time (US/Eastern).
    """
    try:
        parsed = datetime.strptime(date, '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError('date must be in YYYY-MM-DD format') from exc

    service = MatchService()
    matches = await service.get_matches_for_date(parsed)
    grouped = await service.group_matches_by_stream_room(matches)
    return [
        StreamRoomBlock(
            stream_room=room.name if room else None,
            matches=[_summarize(m) for m in room_matches],
        )
        for room, room_matches in grouped.values()
    ]


async def match_operations_report(
    start: datetime,
    end: datetime,
    tenant: TenantArg = None,
    tournament_id: Optional[int] = None,
) -> dict:
    """Operational statistics for matches in a window: start delays, durations.

    Requires admin access.
    """
    return await ReportsService().match_operations(
        start=start, end=end, tournament_id=tournament_id,
    )


def register_tools(mcp: FastMCP) -> None:
    register(mcp, list_matches, gate=Gate.ACTOR, title='List matches')
    register(mcp, get_match, gate=Gate.ACTOR, title='Get match')
    register(mcp, get_schedule, gate=Gate.ACTOR, title='Get daily schedule')
    register(
        mcp, match_operations_report, gate=Gate.ADMIN,
        title='Match operations report',
    )
