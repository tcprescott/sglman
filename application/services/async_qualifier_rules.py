"""Async qualifier — pure rule helpers (no I/O).

Side-effect-free validators and predicates lifted out of
:class:`AsyncQualifierService` so that module stays focused on orchestration.
Mirrors the existing ``async_qualifier_config`` / ``async_qualifier_scoring``
sibling helpers.
"""

from datetime import datetime, timezone
from typing import Optional, Tuple

from application.services.async_qualifier_scoring import DEFAULT_PAR_SAMPLE_SIZE
from models import AsyncQualifier, User

DEFAULT_IMBALANCE_THRESHOLD = 2


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


def is_results_public(qualifier: AsyncQualifier, now: Optional[datetime] = None) -> bool:
    """Active-window information lockdown: pool/par/other entrants' runs and the
    leaderboard go public only once the qualifier closes (inactive or past
    ``closes_at``)."""
    now = now or datetime.now(timezone.utc)
    if not qualifier.is_active:
        return True
    return qualifier.closes_at is not None and now >= qualifier.closes_at
