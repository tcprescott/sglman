"""
Availability window algorithms - shared pure logic.

Player and volunteer availability are the same shape: a set of windows, each with
a ``starts_at``/``ends_at``/``status``, that get resolved against a query range.
These helpers hold the pure algorithms (precedence resolution, segment splitting,
per-user grouping) so both services share one implementation instead of clones.

The functions operate over anything matching :class:`AvailabilityWindow` — the
ORM ``PlayerAvailability`` and ``VolunteerAvailability`` rows both satisfy it.
"""

from datetime import datetime
from typing import Dict, List, Optional, Protocol, Sequence, Tuple, TypeVar

from models import VolunteerAvailabilityStatus


class AvailabilityWindow(Protocol):
    """Structural type both availability row models satisfy."""

    starts_at: datetime
    ends_at: datetime
    status: VolunteerAvailabilityStatus


class UserAvailabilityWindow(AvailabilityWindow, Protocol):
    """An availability window that also carries the owning ``user_id``."""

    user_id: int


W = TypeVar('W', bound=AvailabilityWindow)
UW = TypeVar('UW', bound=UserAvailabilityWindow)


def covers(
    windows: Sequence[AvailabilityWindow], start: datetime, end: datetime,
) -> Optional[VolunteerAvailabilityStatus]:
    """Return the strongest availability signal for a time window.

    PREFERRED beats AVAILABLE; an overlapping UNAVAILABLE window wins outright.
    Returns None when no window overlaps the range.
    """
    result: Optional[VolunteerAvailabilityStatus] = None
    for w in windows:
        if w.starts_at < end and w.ends_at > start:
            if w.status == VolunteerAvailabilityStatus.UNAVAILABLE:
                return VolunteerAvailabilityStatus.UNAVAILABLE
            if w.status == VolunteerAvailabilityStatus.PREFERRED:
                result = VolunteerAvailabilityStatus.PREFERRED
            elif result is None:
                result = VolunteerAvailabilityStatus.AVAILABLE
    return result


def effective_segments(
    windows: Sequence[AvailabilityWindow], start: datetime, end: datetime,
) -> List[Tuple[datetime, datetime, Optional[VolunteerAvailabilityStatus]]]:
    """Split ``[start, end]`` into maximal segments of constant availability.

    Overlapping windows are resolved by :func:`covers` precedence
    (unavailable > preferred > available). Segments with no overlapping
    window carry a ``None`` status. Adjacent segments of equal status are
    merged so the result is the minimal set of contiguous spans.
    """
    if end <= start:
        return []
    boundaries = {start, end}
    for w in windows:
        if w.ends_at > start and w.starts_at < end:
            boundaries.add(max(w.starts_at, start))
            boundaries.add(min(w.ends_at, end))
    points = sorted(boundaries)
    segments: List[Tuple[datetime, datetime, Optional[VolunteerAvailabilityStatus]]] = []
    for seg_start, seg_end in zip(points, points[1:]):
        status = covers(windows, seg_start, seg_end)
        if segments and segments[-1][2] == status:
            segments[-1] = (segments[-1][0], seg_end, status)
        else:
            segments.append((seg_start, seg_end, status))
    return segments


def group_by_user(rows: Sequence[UW]) -> Dict[int, List[UW]]:
    """Group availability rows by their ``user_id`` (insertion order preserved)."""
    out: Dict[int, List[UW]] = {}
    for row in rows:
        out.setdefault(row.user_id, []).append(row)
    return out
