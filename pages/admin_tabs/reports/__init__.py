"""Admin Reports package.

Dispatches to a specific report based on the ``report`` query-string param.
Falls back to the summary dashboard.
"""

from typing import Optional

from .audit import audit_page
from .capacity import capacity_page
from .crew import crew_page
from .dashboard import dashboard_page
from .match_ops import match_ops_page
from .stream_rooms import stream_rooms_page


_REPORT_HANDLERS = {
    'capacity': capacity_page,
    'match_ops': match_ops_page,
    'crew': crew_page,
    'stream_rooms': stream_rooms_page,
    'audit': audit_page,
}


async def reports_page(
    report: Optional[str] = None,
    **params,
) -> None:
    """Top-level entry called from the admin tabs config."""
    handler = _REPORT_HANDLERS.get(report)
    if handler is None:
        await dashboard_page()
        return
    await handler(**params)


__all__ = ['reports_page']
