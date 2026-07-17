"""
Reporting shared constants and helpers.

:class:`ReportsService` (point-in-time snapshots) and :class:`AnalyticsService`
(trends/health) run the same underlying time math. These shared constants and
helpers keep their assumptions in lockstep — most importantly the
``ON_TIME_THRESHOLD_MIN`` that both "on-time %" figures depend on, so the Reports
and Insights dashboards can never silently disagree.
"""

from datetime import datetime
from typing import Optional

from application.utils.timezone import to_eastern


# Fallback match length (minutes) when a match has no finish time and its
# tournament defines no average duration.
DEFAULT_MATCH_DURATION_MIN = 90

# A match counts as "on time" when its start delay is within this many minutes
# (absolute) of the scheduled time. Shared so every on-time percentage agrees.
ON_TIME_THRESHOLD_MIN = 5


def eastern(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert a UTC-aware datetime to US/Eastern, passing ``None`` through."""
    return to_eastern(dt)


def window_hours(start: Optional[datetime], end: Optional[datetime]) -> float:
    """Non-negative hours spanned by ``[start, end]`` (0.0 for missing/inverted)."""
    if not start or not end:
        return 0.0
    return max(0.0, (end - start).total_seconds() / 3600.0)
