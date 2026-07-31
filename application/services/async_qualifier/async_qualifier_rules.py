"""Async qualifier — pure rule helpers (no I/O).

Side-effect-free validators and predicates lifted out of
:class:`AsyncQualifierService` so that module stays focused on orchestration.
Mirrors the existing ``async_qualifier_config`` / ``async_qualifier_scoring``
sibling helpers.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Sequence, Tuple

from application.services.async_qualifier.async_qualifier_scoring import DEFAULT_PAR_SAMPLE_SIZE
from application.utils.duration import format_hms
from models import AsyncQualifier, User

DEFAULT_IMBALANCE_THRESHOLD = 2

# How long a drawn run may stay in progress before it is forfeited automatically.
# Twelve hours is SahasrahBot's production-tested value: comfortably longer than
# any real run plus a meal break, short enough that an abandoned run frees its
# pool slot the same day.
DEFAULT_RUN_TIME_LIMIT_HOURS = 12
# How long before that deadline the runner gets one warning DM.
DEFAULT_EXPIRY_WARNING_MINUTES = 60

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


def run_time_limit(qualifier: Optional[AsyncQualifier]) -> timedelta:
    """How long a run of this qualifier may stay in progress."""
    if qualifier and isinstance(qualifier.config, dict):
        value = qualifier.config.get('run_time_limit_hours')
        if isinstance(value, int) and value >= 1:
            return timedelta(hours=value)
    return timedelta(hours=DEFAULT_RUN_TIME_LIMIT_HOURS)


def expiry_warning_lead(qualifier: Optional[AsyncQualifier]) -> timedelta:
    """How long before the deadline the runner is warned."""
    if qualifier and isinstance(qualifier.config, dict):
        value = qualifier.config.get('expiry_warning_minutes')
        if isinstance(value, int) and value >= 1:
            return timedelta(minutes=value)
    return timedelta(minutes=DEFAULT_EXPIRY_WARNING_MINUTES)


def run_deadline(qualifier: AsyncQualifier, started_at: Optional[datetime]) -> Optional[datetime]:
    """When a run started at ``started_at`` expires — ``None`` if never started.

    Naive values are read as UTC, matching :func:`measure_elapsed` and the
    storage convention.
    """
    if started_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return started_at + run_time_limit(qualifier)


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


class RunUnavailableReason(str, Enum):
    """Why a player cannot start a run right now.

    ``get_player_pools`` returns an empty list for five distinct situations and the
    page used to collapse them into one sentence — leaving the runner unable to
    tell whether to wait, ask an organiser, or go home. Only two of these are
    something an organiser can fix.
    """

    NOT_ACTIVE = 'not_active'
    NOT_OPEN_YET = 'not_open_yet'
    CLOSED = 'closed'
    NO_POOLS = 'no_pools'
    ALL_SLOTS_USED = 'all_slots_used'
    PERMALINKS_EXHAUSTED = 'permalinks_exhausted'
    ANONYMOUS = 'anonymous'


@dataclass(frozen=True)
class PoolUsage:
    """One pool's per-player state: how many of its runs are spent, and whether
    an undrawn permalink is left."""

    pool_id: int
    name: str
    used: int
    allowed: int
    has_candidates: bool
    # Whether the pool holds any permalink a self-paced runner could ever draw. A
    # live-race-only pool holds none, and would otherwise look permanently like
    # "slots free, every seed played" — the one reason that tells an organiser to
    # add more seeds.
    seeded: bool = True

    @property
    def slots_left(self) -> int:
        return max(0, self.allowed - self.used)


@dataclass(frozen=True)
class ReattemptAllowance:
    """What a player has spent of their own reattempt allowance, and what is left.

    A reviewer-granted reattempt is deliberately **not** counted here: it does not
    consume the runner's allowance, so it must not shrink what they may still
    spend themselves.
    """

    spent: int
    allowed: int

    @property
    def remaining(self) -> int:
        return max(0, self.allowed - self.spent)


def describe_unavailability(
    reason: RunUnavailableReason,
    *,
    runs_per_pool: int = 0,
    opens_display: str = '',
    closes_display: str = '',
) -> str:
    """The sentence each reason owes the runner — what to do, not just that they can't."""
    if reason is RunUnavailableReason.ANONYMOUS:
        return "Sign in to start a run."
    if reason is RunUnavailableReason.NOT_ACTIVE:
        return "This qualifier isn't accepting runs."
    if reason is RunUnavailableReason.NOT_OPEN_YET:
        when = f' {opens_display}' if opens_display else ' soon'
        return f"This qualifier opens{when}."
    if reason is RunUnavailableReason.CLOSED:
        when = f' {closes_display}' if closes_display else ''
        return f"This qualifier closed{when}. The leaderboard is below."
    if reason is RunUnavailableReason.NO_POOLS:
        return "No pools have been set up yet — check back, or ask an organiser."
    if reason is RunUnavailableReason.ALL_SLOTS_USED:
        return f"You've used all {runs_per_pool} of your runs in every pool."
    return ("You've played every seed available in the pools you have runs left in. "
            "An organiser needs to add more.")


def classify_availability(
    usages: Sequence[PoolUsage], *, window_reason: Optional[RunUnavailableReason] = None
) -> Optional[RunUnavailableReason]:
    """Why an empty pool list is empty — ``None`` when a run can be started.

    The two exhaustion reasons are the distinction the page could never make:
    a pool is out of *slots* when the player has spent them all, and out of
    *seeds* when it has slots to spare but no undrawn permalink. Only the second
    is something an organiser can fix, so a pool in that state wins the report.
    """
    if window_reason is not None:
        return window_reason
    runnable = [u for u in usages if u.seeded]
    if not runnable:
        return RunUnavailableReason.NO_POOLS
    if any(u.has_candidates and u.slots_left > 0 for u in runnable):
        return None
    if any(u.slots_left > 0 for u in runnable):
        return RunUnavailableReason.PERMALINKS_EXHAUSTED
    return RunUnavailableReason.ALL_SLOTS_USED


def window_reason(qualifier: AsyncQualifier, now: Optional[datetime] = None) -> Optional[RunUnavailableReason]:
    """The window's own verdict, as a reason rather than the ``ValueError``
    ``ensure_window_open`` raises — a shut window is an answer, not an error."""
    now = now or datetime.now(timezone.utc)
    if not qualifier.is_active:
        return RunUnavailableReason.NOT_ACTIVE
    if qualifier.opens_at is not None and now < qualifier.opens_at:
        return RunUnavailableReason.NOT_OPEN_YET
    if qualifier.closes_at is not None and now >= qualifier.closes_at:
        return RunUnavailableReason.CLOSED
    return None


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
