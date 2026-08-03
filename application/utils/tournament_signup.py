"""Where a tournament's player signup window stands right now.

Pure and dependency-free on purpose. The same three states drive the Tournaments
tab's button, the service's refusal message, the admin table's chip and the REST
payload, and four hand-rolled ``if closes_at and closes_at < now`` chains would
eventually disagree with each other about the boundary.

Both bounds are optional and read permissively — an unset ``signups_open_at``
means signups are open now, an unset ``signups_close_at`` means they stay open —
so a tournament that never set either is ``OPEN``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

__all__ = ['SignupWindow', 'signup_window_is_open', 'signup_window_state']


class SignupWindow(str, Enum):
    UPCOMING = 'upcoming'
    OPEN = 'open'
    CLOSED = 'closed'


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    """UTC-aware form of a stored bound, or ``None``.

    SQLite (the test database) hands back naive datetimes where Postgres returns
    aware ones, and comparing the two raises. Storage is UTC either way, so a
    naive value is stamped rather than converted.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def signup_window_state(
    opens_at: Optional[datetime],
    closes_at: Optional[datetime],
    now: Optional[datetime] = None,
) -> SignupWindow:
    """Which of the three states the window is in at ``now`` (default: now, UTC)."""
    moment = now or datetime.now(timezone.utc)
    moment = _aware(moment) or moment
    opens_at = _aware(opens_at)
    closes_at = _aware(closes_at)
    if opens_at is not None and moment < opens_at:
        return SignupWindow.UPCOMING
    if closes_at is not None and moment >= closes_at:
        return SignupWindow.CLOSED
    return SignupWindow.OPEN


def signup_window_is_open(
    opens_at: Optional[datetime],
    closes_at: Optional[datetime],
    now: Optional[datetime] = None,
) -> bool:
    return signup_window_state(opens_at, closes_at, now) is SignupWindow.OPEN
