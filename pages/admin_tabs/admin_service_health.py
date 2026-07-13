"""Admin Service Health tab — tenant read-only subset (STAFF).

The full external-service board lives on the SUPER_ADMIN ``/platform`` surface;
this tab shows a tenant's STAFF only the dependencies *their* tenant relies on —
its authorized racetime bots and its own Challonge connection — with the same
status badges. Read-only: there is no probe-refresh button here (the platform
worker keeps the shared board warm); this view probes the tenant's own subset live
on load so a staffer can see, e.g., their Challonge token expiring before it breaks
a race day.
"""

from nicegui import ui

from application.services import ServiceHealthService
from application.tenant_context import get_current_tenant_id
from pages.service_health_view import build_refreshable_board


async def admin_service_health_page() -> None:
    with ui.column().classes('page-container-narrow'):
        with ui.row().classes('header-row'):
            ui.label('Service Health').classes('page-title')

        ui.separator().classes('separator-spacing')

        ui.label(
            'Health of the external services your tenant depends on — your '
            'authorized racetime bots and your Challonge connection. A credential '
            "warning (e.g. an expiring Challonge token) means reconnect before it "
            'becomes an outage.'
        ).classes('text-caption text-grey')

        tenant_id = get_current_tenant_id()
        health = ServiceHealthService()

        async def _load():
            if tenant_id is None:
                return []
            return await health.tenant_subset(tenant_id)

        build_refreshable_board(_load)
