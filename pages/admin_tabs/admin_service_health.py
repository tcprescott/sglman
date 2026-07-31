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

from application.services import ServiceHealthService, ServiceStatus
from application.tenant_context import get_current_tenant_id
from pages.admin_tabs.links import CHALLONGE, admin_url
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

        build_refreshable_board(_load, action_for=_route_out)


def _route_out(result) -> tuple | None:
    """The page a staff member fixes this row on, when there is one.

    The blurb above tells them to "reconnect before it becomes an outage" and
    used to leave them to find the tab themselves. Only Challonge gets a link:
    a racetime bot is platform-managed and granted to the tenant by a
    super-admin, so there is nothing a community's staff can do about an
    unhealthy one — and a link that lands on a page which cannot fix it is
    worse than none.
    """
    if result.key == 'challonge' and result.status is not ServiceStatus.HEALTHY:
        return ('Reconnect on the Challonge tab', admin_url(CHALLONGE))
    return None
