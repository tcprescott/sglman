"""Async qualifier — pure rule helpers (no I/O).

Side-effect-free validators and predicates lifted out of
:class:`AsyncQualifierService` so that module stays focused on orchestration.
Mirrors the existing ``async_qualifier_config`` / ``async_qualifier_scoring``
sibling helpers.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Tuple

from application.services.async_qualifier.async_qualifier_scoring import DEFAULT_PAR_SAMPLE_SIZE
from application.utils.duration import format_hms
from models import AsyncQualifier, User

DEFAULT_IMBALANCE_THRESHOLD = 2

# Clock skew between the browser's submit and the server's ``now``, plus request
# latency. A claim inside this much of the measured duration is not a discrepancy.
CLOCK_GRACE_SECONDS = 120

# How far a claim may fall short of the measurement before the player is asked
# about it. Generous on purpose: finishing and submitting twenty minutes later is
# ordinary, while a dropped H segment is off by an hour or more.
IMPLAUSIBLE_DRIFT_SECONDS = 15 * 60


def validate_counts(runs_per_pool: int, allowed_reattempts: int) -> Tuple[int, int]:
    if runs_per_pool < 1:
        raise ValueError("Runs per pool must be at least 1")
    if allowed_reattempts < 0:
        raise ValueError("Allowed reattempts cannot be negative")
    return runs_per_pool, allowed_reattempts


def validate_window(opens_at: Optional[datetime], closes_at: Optional[datetime]) -> None:
    if opens_at is not None and closes_at is not None and closes_at <= opens_at:
        raise ValueError("The close time must be after the open time")


def par_sample_size(qualifier: Optional[AsyncQualifier]) -> int:
    if qualifier and isinstance(qualifier.config, dict):
        value = qualifier.config.get('par_sample_size')
        if isinstance(value, int) and value >= 1:
            return value
    return DEFAULT_PAR_SAMPLE_SIZE


def imbalance_threshold(qualifier: AsyncQualifier) -> int:
    if isinstance(qualifier.config, dict):
        value = qualifier.config.get('draw_imbalance_threshold')
        if isinstance(value, int) and value >= 1:
            return value
    return DEFAULT_IMBALANCE_THRESHOLD


def display_name(user: User) -> str:
    return user.display_name or user.username or f"User {user.id}"


def ensure_window_open(qualifier: AsyncQualifier) -> None:
    if not qualifier.is_active:
        raise ValueError("This qualifier is not active")
    now = datetime.now(timezone.utc)
    if qualifier.opens_at is not None and now < qualifier.opens_at:
        raise ValueError("This qualifier has not opened yet")
    if qualifier.closes_at is not None and now >= qualifier.closes_at:
        raise ValueError("This qualifier has closed")


class ClaimVerdict(str, Enum):
    """How a claimed finish time stands against the server-measured wall clock."""

    OK = 'ok'
    IMPLAUSIBLE = 'implausible'   # ask the player; never blocks
    IMPOSSIBLE = 'impossible'     # refuse; the claim exceeds the wall clock


def measure_elapsed(started_at: Optional[datetime], now: Optional[datetime] = None) -> Optional[int]:
    """Whole seconds since ``started_at``, or ``None`` when it was never stamped.

    Naive values are read as UTC — the storage convention — so the page ticker,
    the service and the reviewer's card all measure the same interval.
    """
    if started_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return max(0, int((now - started_at).total_seconds()))


def classify_claim(claimed_seconds: int, measured_seconds: Optional[int]) -> ClaimVerdict:
    """Compare a claimed finish time against the server-measured wall clock.

    ``measured`` is an upper bound by construction — a run cannot have taken
    longer than the time since it started — so a claim above it (past the clock
    grace) is refusable. A claim *below* it is the normal case, because the timer
    keeps running while the player reads the seed and gets around to submitting;
    only a large shortfall is worth asking about, and asking must never block.
    """
    if measured_seconds is None:
        return ClaimVerdict.OK
    if claimed_seconds > measured_seconds + CLOCK_GRACE_SECONDS:
        return ClaimVerdict.IMPOSSIBLE
    if measured_seconds - claimed_seconds >= IMPLAUSIBLE_DRIFT_SECONDS:
        return ClaimVerdict.IMPLAUSIBLE
    return ClaimVerdict.OK


def describe_claim(claimed_seconds: int, measured_seconds: int) -> str:
    """One sentence naming both numbers, for the refusal and the runner's prompt."""
    return (f"Your run has been going {format_hms(measured_seconds)}, so a finish time of "
            f"{format_hms(claimed_seconds)} is longer than the run itself.")


def is_results_public(qualifier: AsyncQualifier, now: Optional[datetime] = None) -> bool:
    """Active-window information lockdown: pool/par/other entrants' runs and the
    leaderboard go public only once the qualifier closes (inactive or past
    ``closes_at``)."""
    now = now or datetime.now(timezone.utc)
    if not qualifier.is_active:
        return True
    return qualifier.closes_at is not None and now >= qualifier.closes_at
