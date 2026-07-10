"""Admin Reports package.

Dispatches to a specific report based on the ``report`` query-string param.
Falls back to the summary dashboard.
"""

from typing import Optional

from nicegui import app, background_tasks

from application.services import TelemetryService
from .audit import audit_page
from .capacity import capacity_page
from .crew import crew_page
from .dashboard import dashboard_page
from .insights import insights_page
from .match_ops import match_ops_page
from .stream_rooms import stream_rooms_page
from .telemetry import telemetry_page
from .volunteers import volunteers_page


_REPORT_HANDLERS = {
    'insights': insights_page,
    'capacity': capacity_page,
    'match_ops': match_ops_page,
    'crew': crew_page,
    'stream_rooms': stream_rooms_page,
    'volunteers': volunteers_page,
    'audit': audit_page,
    'telemetry': telemetry_page,
}


def _track_report_view(report: str) -> None:
    """Fire-and-forget an interaction row when a specific report is opened.

    Only called for an explicit ``report`` (not the dashboard landing), so a
    plain ``/admin`` load — where every tab panel renders eagerly — does not
    manufacture a spurious report view.
    """
    try:
        background_tasks.create(
            TelemetryService().track_interaction(
                event_type='report.viewed',
                path=report,
                discord_id=app.storage.user.get('discord_id'),
                username=app.storage.user.get('username'),
                session_id=app.storage.browser.get('id'),
            )
        )
    except Exception:
        pass


async def reports_page(
    report: Optional[str] = None,
    **params,
) -> None:
    """Top-level entry called from the admin tabs config."""
    handler = _REPORT_HANDLERS.get(report)
    if handler is None:
        await dashboard_page()
        return
    _track_report_view(report)
    await handler(**params)


__all__ = ['reports_page']
