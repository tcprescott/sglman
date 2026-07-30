"""Admin Reports package.

Dispatches to a specific report based on the ``report`` query-string param.
Falls back to the summary dashboard.
"""

from typing import Optional

from nicegui import app, background_tasks

from application.services import FeatureFlagService, TelemetryService
from models import FeatureFlag
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

# Reports whose subsystem is behind a per-tenant flag. A community that has
# never enabled volunteer scheduling used to get a Volunteer Coverage card, open
# it, and read volunteer data — the report was the only entry surface that did
# not check (REST mounts behind require_feature, the MCP tool declares the flag,
# both Vol. tabs test it). The service now refuses too; this is the surface half.
_REPORT_FEATURES = {
    'volunteers': FeatureFlag.VOLUNTEERS,
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
    # One query for every report and every dashboard card, rather than an
    # is_enabled call in each module.
    live = await FeatureFlagService().enabled_flags()
    feature = _REPORT_FEATURES.get(report)
    if feature is not None and feature not in live:
        report = None
    handler = _REPORT_HANDLERS.get(report)
    if handler is None:
        await dashboard_page(live=live)
        return
    _track_report_view(report)
    await handler(**params)


__all__ = ['reports_page']
