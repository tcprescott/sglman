"""Everything one person is committed to, as blocks on a clock.

My Schedule's Timeline view: the matches they play, the matches they crew and
their volunteer shifts, merged into one list of time ranges. The merge lives
here rather than in the page because it spans three models; the page only
draws boxes. Lane placement and the event-day rule are pure functions so they
are testable without a database.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, List, Optional, Sequence, Tuple

from application.repositories import MatchRepository, VolunteerAssignmentRepository
from application.services.crew_service import CrewService
from application.services.system_config_service import SystemConfigService
from application.utils.timezone import local_day_bounds, to_local, to_utc_aware
from models import User

MATCH = 'match'
CREW = 'crew'
SHIFT = 'shift'

#: An event day runs 06:00 to 06:00, as on the volunteer grids, so a match at
#: 01:00 sits on the evening it belongs to.
DAY_STARTS_AT_HOUR = 6

_ROLE_TITLES = {'commentator': 'Commentary', 'tracker': 'Tracking'}


@dataclass(frozen=True)
class TimelineItem:
    kind: str
    starts_at: datetime
    ends_at: datetime
    title: str
    detail: str
    match_id: int = 0
    #: The shift's assignment, for its details dialog.
    assignment: Any = None


@dataclass(frozen=True)
class Placed:
    item: TimelineItem
    lane: int
    lanes: int


def event_day(moment: datetime, tz: Any = None) -> date:
    local = to_local(moment, tz) or moment
    return (local - timedelta(hours=DAY_STARTS_AT_HOUR)).date()


def place_in_lanes(items: Sequence[TimelineItem]) -> List[Placed]:
    """Side by side where items overlap; each overlapping group shares the width."""
    placed: List[Placed] = []
    group: List[Tuple[TimelineItem, int]] = []
    lane_ends: List[datetime] = []
    group_end: Optional[datetime] = None

    def close_group() -> None:
        placed.extend(Placed(item, lane, len(lane_ends)) for item, lane in group)

    for item in sorted(items, key=lambda i: (i.starts_at, i.ends_at)):
        if group_end is not None and item.starts_at >= group_end:
            close_group()
            group, lane_ends, group_end = [], [], None
        lane = next((i for i, end in enumerate(lane_ends) if end <= item.starts_at), None)
        if lane is None:
            lane = len(lane_ends)
            lane_ends.append(item.ends_at)
        else:
            lane_ends[lane] = item.ends_at
        group.append((item, lane))
        group_end = item.ends_at if group_end is None else max(group_end, item.ends_at)
    close_group()
    return placed


def opening_day(days: Sequence[date], today: date) -> Optional[date]:
    """Today during the event, else the next day with something on, else the last."""
    if not days:
        return None
    if today in days:
        return today
    return next((d for d in days if d > today), days[-1])


class MyTimelineService:
    def __init__(self) -> None:
        self.match_repository = MatchRepository()
        self.assignment_repository = VolunteerAssignmentRepository()
        self.crew_service = CrewService()

    async def window(self) -> Tuple[datetime, datetime]:
        """The event's days on the viewer's clock, each running 06:00 to 06:00."""
        start, end = await SystemConfigService.get_event_window()
        lo, hi = local_day_bounds(start, end)
        shift = timedelta(hours=DAY_STARTS_AT_HOUR)
        return lo + shift, hi + shift

    async def items(self, user: User, *, include_shifts: bool) -> List[TimelineItem]:
        """``include_shifts`` is the caller's ``FeatureFlag.VOLUNTEERS`` check."""
        start, end = await self.window()
        crew_roles = {
            row['match_id']: row['role']
            for row in await self.crew_service.list_my_commitments(user, upcoming_only=False)
        }
        items: List[TimelineItem] = []
        for match in await self.match_repository.commitments_for_user(user.id, start, end):
            items.append(self._match_item(match, user, crew_roles.get(match.id)))
        if include_shifts:
            for assignment in await self.assignment_repository.list_for_user(user, with_shiftmates=True):
                shift = assignment.shift
                if shift.ends_at <= start or shift.starts_at >= end:
                    continue
                items.append(TimelineItem(
                    kind=SHIFT,
                    starts_at=to_utc_aware(shift.starts_at),
                    ends_at=to_utc_aware(shift.ends_at),
                    title=shift.position.name if shift.position else 'Volunteer',
                    detail=shift.label or '',
                    assignment=assignment,
                ))
        items.sort(key=lambda i: i.starts_at)
        return items

    @staticmethod
    def _match_item(match: Any, user: User, crew_role: Optional[str]) -> TimelineItem:
        tournament = match.tournament
        minutes = (
            getattr(tournament, 'average_match_duration', None)
            or CrewService.DEFAULT_MATCH_MINUTES
        )
        starts_at = to_utc_aware(match.scheduled_at)
        short = tournament.short_label if tournament else ''
        players = [p for p in match.players if p.user]
        playing = any(p.user_id == user.id for p in players)
        if playing or crew_role is None:
            opponents = [p.user.preferred_name for p in players if p.user_id != user.id]
            return TimelineItem(
                kind=MATCH, starts_at=starts_at, ends_at=starts_at + timedelta(minutes=minutes),
                title=('vs ' + ', '.join(opponents)) if opponents else (match.title or 'Your match'),
                detail=short, match_id=match.id,
            )
        names = ' vs '.join(p.user.preferred_name for p in players)
        return TimelineItem(
            kind=CREW, starts_at=starts_at, ends_at=starts_at + timedelta(minutes=minutes),
            title=_ROLE_TITLES.get(crew_role, 'Crew'),
            detail=' · '.join(part for part in (names, short) if part),
            match_id=match.id,
        )
